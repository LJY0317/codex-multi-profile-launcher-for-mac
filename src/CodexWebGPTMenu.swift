import AppKit
import SwiftUI

private struct Approval: Codable, Identifiable {
  let traceId: String
  let tabId: String
  var id: String { "\(traceId)|\(tabId)" }
}
private struct MenuStatus: Codable { let account: String; let status: String; let approvals: [Approval] }
private struct ControlDescriptor: Codable {
  struct Control: Codable { let endpoint: String; let token: String }
  let control: Control
}
private enum BridgeState: Equatable {
  case connected, busy, stopped, unavailable, unknown
  var title: String {
    switch self {
    case .connected: return "연결됨"
    case .busy: return "작업 중"
    case .stopped: return "종료됨"
    case .unavailable: return "연결 불가"
    case .unknown: return "확인 불가"
    }
  }
}
private struct AccountSnapshot { var state: BridgeState = .unknown; var approvals: [Approval] = []; var failures = 0 }

@MainActor
private final class MenuController: ObservableObject {
  @Published private var accounts = [1: AccountSnapshot(), 2: AccountSnapshot()]
  private let home = FileManager.default.homeDirectoryForCurrentUser
  private let menuLaunchAgent = "local.codex-web-gpt.common-menu"
  private var timer: Timer?

  init() { DispatchQueue.main.async { self.refresh() } }
  deinit { timer?.invalidate() }
  func snapshot(_ account: Int) -> AccountSnapshot { accounts[account] ?? AccountSnapshot() }
  var hasApprovals: Bool { accounts.values.contains { !$0.approvals.isEmpty } }
  func accountTitle(_ account: Int) -> String {
    let value = snapshot(account)
    let pending = value.approvals.isEmpty ? "" : " / 승인 대기 \(value.approvals.count)"
    return "Account \(account) — \(value.state.title)\(pending)"
  }
  func shouldStop(_ account: Int) -> Bool {
    let state = snapshot(account).state
    return state == .connected || state == .busy
  }
  func canStop(_ account: Int) -> Bool { snapshot(account).state != .busy }

  func openChatGPT(_ account: Int) { openApp("ChatGPT (\(account))", hidden: false) }
  func openBridge(_ account: Int) { openApp("Codex Web GPT (\(account))", hidden: false) }
  func startBridge(_ account: Int) { openApp("Codex Web GPT (\(account))", hidden: true) }
  private func openApp(_ name: String, hidden: Bool) {
    let url = home.appendingPathComponent("Applications/\(name).app")
    guard FileManager.default.fileExists(atPath: url.path) else { return }
    let configuration = NSWorkspace.OpenConfiguration()
    if hidden { configuration.arguments = ["--hidden"] }
    NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in }
  }

  func openApproval(_ account: Int, _ approval: Approval) {
    request(account, "/v1/menu/open-approval", ["traceId": approval.traceId, "tabId": approval.tabId]) { [weak self] _ in self?.refresh() }
  }
  func stopBridge(_ account: Int) {
    request(account, "/v1/menu/stop", [:]) { [weak self] _ in self?.refresh() }
  }

  func loginEnabled(_ label: String) -> Bool {
    FileManager.default.fileExists(atPath: launchAgentURL(label).path)
  }
  func setMenuLogin(_ enabled: Bool) {
    setLaunchAgent(menuLaunchAgent, enabled, Bundle.main.executableURL?.path ?? CommandLine.arguments[0], [])
  }
  func setBridgeLogin(_ account: Int, _ enabled: Bool) {
    let executable = home.appendingPathComponent("Applications/Codex Web GPT (\(account)).app/Contents/MacOS/launcher").path
    setLaunchAgent("local.codex-web-gpt.bridge.account\(account)", enabled, executable, ["--hidden"])
  }
  private func launchAgentURL(_ label: String) -> URL {
    home.appendingPathComponent("Library/LaunchAgents/\(label).plist")
  }
  private func setLaunchAgent(_ label: String, _ enabled: Bool, _ command: String, _ arguments: [String]) {
    let url = launchAgentURL(label)
    if !enabled { try? FileManager.default.removeItem(at: url); return }
    guard FileManager.default.isExecutableFile(atPath: command) else { return }
    let plist: [String: Any] = ["Label": label, "ProgramArguments": [command] + arguments, "RunAtLoad": true, "ProcessType": "Background"]
    guard let data = try? PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0) else { return }
    try? data.write(to: url, options: .atomic)
  }

  private func descriptor(_ account: Int) -> ControlDescriptor? {
    let directory = account == 1 ? ".codex-chatgpt-web-account1" : ".codex-chatgpt-web-account2"
    let url = home.appendingPathComponent("\(directory)/runtime/launcher-browser.json")
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(ControlDescriptor.self, from: data)
  }
  func refresh() {
    timer?.invalidate()
    let group = DispatchGroup()
    for account in [1, 2] {
      group.enter()
      fetch(account) { [weak self] value in
        if let value { self?.accounts[account] = value }
        group.leave()
      }
    }
    group.notify(queue: .main) { [weak self] in
      guard let self else { return }
      let failures = self.accounts.values.map(\.failures).max() ?? 0
      let interval = min(120, 15 * pow(2, Double(min(failures, 3))))
      self.timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
        Task { @MainActor in self?.refresh() }
      }
    }
  }
  private func fetch(_ account: Int, completion: @escaping (AccountSnapshot?) -> Void) {
    guard let descriptor = descriptor(account), let base = URL(string: descriptor.control.endpoint),
          let url = URL(string: "/v1/menu/status", relativeTo: base) else {
      var value = snapshot(account); value.state = .stopped; value.approvals = []; value.failures = 0; completion(value); return
    }
    var request = URLRequest(url: url)
    request.setValue("Bearer \(descriptor.control.token)", forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 2
    URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
      Task { @MainActor in
        var value = self?.snapshot(account) ?? AccountSnapshot()
        guard error == nil, let http = response as? HTTPURLResponse, http.statusCode == 200,
              let data, let status = try? JSONDecoder().decode(MenuStatus.self, from: data) else {
          value.state = .unavailable; value.approvals = []; value.failures += 1; completion(value); return
        }
        value.state = status.status == "connected" ? .connected : status.status == "busy" ? .busy : .unknown
        value.approvals = status.approvals; value.failures = 0; completion(value)
      }
    }.resume()
  }
  private func request(_ account: Int, _ path: String, _ body: [String: String], completion: @escaping (Bool) -> Void) {
    guard let descriptor = descriptor(account), let base = URL(string: descriptor.control.endpoint),
          let url = URL(string: path, relativeTo: base) else { completion(false); return }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(descriptor.control.token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try? JSONSerialization.data(withJSONObject: body)
    URLSession.shared.dataTask(with: request) { _, response, _ in
      DispatchQueue.main.async { completion((response as? HTTPURLResponse)?.statusCode == 200) }
    }.resume()
  }
}

@main
struct CodexWebGPTMenuApp: App {
  @StateObject private var controller = MenuController()
  var body: some Scene {
    MenuBarExtra("Codex Web GPT", systemImage: controller.hasApprovals ? "exclamationmark.circle.fill" : "terminal.fill") {
      accountMenu(1)
      accountMenu(2)
      Divider()
      Menu("공통 설정") {
        Toggle("로그인 시 메뉴 실행", isOn: Binding(get: { controller.loginEnabled("local.codex-web-gpt.common-menu") }, set: { controller.setMenuLogin($0) }))
        Toggle("로그인 시 Account 1 브리지 실행", isOn: Binding(get: { controller.loginEnabled("local.codex-web-gpt.bridge.account1") }, set: { controller.setBridgeLogin(1, $0) }))
        Toggle("로그인 시 Account 2 브리지 실행", isOn: Binding(get: { controller.loginEnabled("local.codex-web-gpt.bridge.account2") }, set: { controller.setBridgeLogin(2, $0) }))
      }
      Divider()
      Button("메뉴 앱 종료 — 브리지와 ChatGPT는 유지") { NSApp.terminate(nil) }
    }
    .menuBarExtraStyle(.menu)
  }
  @ViewBuilder private func accountMenu(_ account: Int) -> some View {
    Menu(controller.accountTitle(account)) {
      Button("ChatGPT (\(account)) 열기") { controller.openChatGPT(account) }
      Button("브리지 런처 (\(account)) 열기") { controller.openBridge(account) }
      Divider()
      let approvals = controller.snapshot(account).approvals
      if approvals.isEmpty {
        Text("승인 요청: 대기 없음")
      } else {
        ForEach(approvals) { approval in
          Button("승인 요청 열기 — \(approval.traceId.prefix(8))") { controller.openApproval(account, approval) }
        }
      }
      Divider()
      if controller.shouldStop(account) {
        Button(controller.canStop(account) ? "브리지 종료" : "브리지 종료 — 활성 작업 대기 중") { controller.stopBridge(account) }
          .disabled(!controller.canStop(account))
      } else {
        Button("브리지 시작") { controller.startBridge(account) }
      }
    }
  }
}
