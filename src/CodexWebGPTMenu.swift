import AppKit
import Foundation

private struct Approval: Codable { let traceId: String; let tabId: String }
private struct MenuStatus: Codable { let account: String; let status: String; let approvals: [Approval] }
private struct ControlDescriptor: Codable {
  struct Control: Codable { let endpoint: String; let token: String }
  let control: Control
}
private enum BridgeState {
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
private struct AccountSnapshot {
  var state: BridgeState = .unknown
  var approvals: [Approval] = []
  var failures = 0
}

@main
final class CodexWebGPTMenu: NSObject, NSApplicationDelegate {
  private let home = FileManager.default.homeDirectoryForCurrentUser
  private let menuLaunchAgent = "local.codex-web-gpt.common-menu"
  private var statusItem: NSStatusItem!
  private var accounts = [1: AccountSnapshot(), 2: AccountSnapshot()]
  private var refreshTimer: Timer?

  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.setActivationPolicy(.accessory)
    statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    statusItem.button?.title = "Codex"
    refreshMenu()
    refreshBridgeStatus()
  }

  func applicationWillTerminate(_ notification: Notification) { refreshTimer?.invalidate() }
  private func wrapper(_ name: String) -> URL { home.appendingPathComponent("Applications/\(name).app") }
  private func descriptorURL(for account: Int) -> URL {
    let directory = account == 1 ? ".codex-chatgpt-web-account1" : ".codex-chatgpt-web-account2"
    return home.appendingPathComponent("\(directory)/runtime/launcher-browser.json")
  }
  private func descriptor(for account: Int) -> ControlDescriptor? {
    guard let data = try? Data(contentsOf: descriptorURL(for: account)) else { return nil }
    return try? JSONDecoder().decode(ControlDescriptor.self, from: data)
  }

  @objc private func openChatGPT1() { openApplication(wrapper("ChatGPT (1)"), hidden: false) }
  @objc private func openChatGPT2() { openApplication(wrapper("ChatGPT (2)"), hidden: false) }
  @objc private func openBridge1() { openApplication(wrapper("Codex Web GPT (1)"), hidden: false) }
  @objc private func openBridge2() { openApplication(wrapper("Codex Web GPT (2)"), hidden: false) }
  @objc private func startBridge1() { openApplication(wrapper("Codex Web GPT (1)"), hidden: true) }
  @objc private func startBridge2() { openApplication(wrapper("Codex Web GPT (2)"), hidden: true) }

  private func openApplication(_ url: URL, hidden: Bool) {
    guard FileManager.default.fileExists(atPath: url.path) else { return }
    let configuration = NSWorkspace.OpenConfiguration()
    if hidden { configuration.arguments = ["--hidden"] }
    NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in }
  }

  private func accountMenu(_ account: Int) -> NSMenuItem {
    let snapshot = accounts[account] ?? AccountSnapshot()
    let approvalSuffix = snapshot.approvals.isEmpty ? "" : " / 승인 대기 \(snapshot.approvals.count)"
    let item = NSMenuItem(title: "Account \(account) — \(snapshot.state.title)\(approvalSuffix)", action: nil, keyEquivalent: "")
    let submenu = NSMenu(title: "Account \(account)")
    submenu.addItem(actionItem("ChatGPT (\(account)) 열기", account == 1 ? #selector(openChatGPT1) : #selector(openChatGPT2)))
    submenu.addItem(actionItem("브리지 런처 (\(account)) 열기", account == 1 ? #selector(openBridge1) : #selector(openBridge2)))
    submenu.addItem(.separator())
    if snapshot.approvals.isEmpty {
      let noApprovals = NSMenuItem(title: "승인 요청: 대기 없음", action: nil, keyEquivalent: "")
      noApprovals.isEnabled = false
      submenu.addItem(noApprovals)
    } else {
      for approval in snapshot.approvals {
        let request = actionItem("승인 요청 열기 — \(String(approval.traceId.prefix(8)))", #selector(openApproval(_:)))
        request.representedObject = "\(account)|\(approval.traceId)|\(approval.tabId)"
        submenu.addItem(request)
      }
    }
    submenu.addItem(.separator())
    if snapshot.state == .connected || snapshot.state == .busy {
      let stop = actionItem("브리지 종료", #selector(stopBridge(_:)))
      stop.representedObject = String(account)
      stop.isEnabled = snapshot.state != .busy
      if snapshot.state == .busy { stop.title = "브리지 종료 — 활성 작업 대기 중" }
      submenu.addItem(stop)
    } else {
      submenu.addItem(actionItem("브리지 시작", account == 1 ? #selector(startBridge1) : #selector(startBridge2)))
    }
    item.submenu = submenu
    return item
  }

  private func actionItem(_ title: String, _ action: Selector) -> NSMenuItem {
    let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
    item.target = self
    return item
  }

  private func refreshMenu() {
    let menu = NSMenu()
    menu.addItem(accountMenu(1)); menu.addItem(accountMenu(2)); menu.addItem(.separator())
    let settings = NSMenuItem(title: "공통 설정", action: nil, keyEquivalent: "")
    let settingsMenu = NSMenu(title: "공통 설정")
    settingsMenu.addItem(toggleItem("로그인 시 메뉴 실행", enabled: launchAgentExists(menuLaunchAgent), action: #selector(toggleMenuLogin(_:)), represented: menuLaunchAgent))
    settingsMenu.addItem(toggleItem("로그인 시 Account 1 브리지 실행", enabled: launchAgentExists(bridgeLaunchAgent(1)), action: #selector(toggleBridgeLogin(_:)), represented: "1"))
    settingsMenu.addItem(toggleItem("로그인 시 Account 2 브리지 실행", enabled: launchAgentExists(bridgeLaunchAgent(2)), action: #selector(toggleBridgeLogin(_:)), represented: "2"))
    settings.submenu = settingsMenu
    menu.addItem(settings); menu.addItem(.separator())
    menu.addItem(actionItem("메뉴 앱 종료 — 브리지와 ChatGPT는 유지", #selector(quitMenuOnly)))
    statusItem.menu = menu
    statusItem.button?.title = accounts.values.contains { !$0.approvals.isEmpty } ? "! Codex" : "Codex"
  }

  private func toggleItem(_ title: String, enabled: Bool, action: Selector, represented: String) -> NSMenuItem {
    let item = actionItem(title, action); item.representedObject = represented; item.state = enabled ? .on : .off
    return item
  }

  @objc private func openApproval(_ sender: NSMenuItem) {
    guard let raw = sender.representedObject as? String else { return }
    let values = raw.split(separator: "|", maxSplits: 2).map(String.init)
    guard values.count == 3, let account = Int(values[0]) else { return }
    request(account: account, path: "/v1/menu/open-approval", method: "POST", body: ["traceId": values[1], "tabId": values[2]]) { [weak self] success in
      if success { self?.refreshBridgeStatus() }
    }
  }
  @objc private func stopBridge(_ sender: NSMenuItem) {
    guard let raw = sender.representedObject as? String, let account = Int(raw) else { return }
    request(account: account, path: "/v1/menu/stop", method: "POST", body: [:]) { [weak self] _ in self?.refreshBridgeStatus() }
  }
  @objc private func toggleMenuLogin(_ sender: NSMenuItem) {
    setLaunchAgent(menuLaunchAgent, enabled: !launchAgentExists(menuLaunchAgent), command: Bundle.main.executableURL?.path ?? CommandLine.arguments[0], arguments: [])
    refreshMenu()
  }
  @objc private func toggleBridgeLogin(_ sender: NSMenuItem) {
    guard let raw = sender.representedObject as? String, let account = Int(raw) else { return }
    let label = bridgeLaunchAgent(account)
    let executable = wrapper("Codex Web GPT (\(account))").appendingPathComponent("Contents/MacOS/launcher").path
    setLaunchAgent(label, enabled: !launchAgentExists(label), command: executable, arguments: ["--hidden"])
    refreshMenu()
  }
  @objc private func quitMenuOnly() { NSApp.terminate(nil) }

  private func bridgeLaunchAgent(_ account: Int) -> String { "local.codex-web-gpt.bridge.account\(account)" }
  private func launchAgentURL(_ label: String) -> URL { home.appendingPathComponent("Library/LaunchAgents/\(label).plist") }
  private func launchAgentExists(_ label: String) -> Bool { FileManager.default.fileExists(atPath: launchAgentURL(label).path) }
  private func setLaunchAgent(_ label: String, enabled: Bool, command: String, arguments: [String]) {
    let url = launchAgentURL(label)
    if !enabled { try? FileManager.default.removeItem(at: url); return }
    guard FileManager.default.isExecutableFile(atPath: command) else { return }
    let plist: [String: Any] = ["Label": label, "ProgramArguments": [command] + arguments, "RunAtLoad": true, "ProcessType": "Background"]
    guard let data = try? PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0) else { return }
    try? data.write(to: url, options: .atomic)
  }

  private func refreshBridgeStatus() {
    refreshTimer?.invalidate()
    let group = DispatchGroup()
    for account in [1, 2] {
      group.enter()
      fetchStatus(account: account) { [weak self] snapshot in
        if let snapshot { self?.accounts[account] = snapshot }
        group.leave()
      }
    }
    group.notify(queue: .main) { [weak self] in
      guard let self else { return }
      self.refreshMenu()
      let failureCount = self.accounts.values.map(\.failures).max() ?? 0
      let delay = min(120, 15 * pow(2, Double(min(failureCount, 3))))
      self.refreshTimer = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in self?.refreshBridgeStatus() }
    }
  }

  private func fetchStatus(account: Int, completion: @escaping (AccountSnapshot?) -> Void) {
    guard let descriptor = descriptor(for: account), let base = URL(string: descriptor.control.endpoint), let url = URL(string: "/v1/menu/status", relativeTo: base) else {
      var snapshot = accounts[account] ?? AccountSnapshot(); snapshot.state = .stopped; snapshot.approvals = []; snapshot.failures = 0; completion(snapshot); return
    }
    var request = URLRequest(url: url); request.setValue("Bearer \(descriptor.control.token)", forHTTPHeaderField: "Authorization"); request.timeoutInterval = 2
    URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
      var snapshot = self?.accounts[account] ?? AccountSnapshot()
      guard error == nil, let http = response as? HTTPURLResponse, http.statusCode == 200, let data, let status = try? JSONDecoder().decode(MenuStatus.self, from: data) else {
        snapshot.state = .unavailable; snapshot.approvals = []; snapshot.failures += 1; completion(snapshot); return
      }
      snapshot.state = status.status == "connected" ? .connected : status.status == "busy" ? .busy : .unknown
      snapshot.approvals = status.approvals; snapshot.failures = 0; completion(snapshot)
    }.resume()
  }

  private func request(account: Int, path: String, method: String, body: [String: String], completion: @escaping (Bool) -> Void) {
    guard let descriptor = descriptor(for: account), let base = URL(string: descriptor.control.endpoint), let url = URL(string: path, relativeTo: base) else { completion(false); return }
    var request = URLRequest(url: url); request.httpMethod = method; request.setValue("Bearer \(descriptor.control.token)", forHTTPHeaderField: "Authorization"); request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.httpBody = try? JSONSerialization.data(withJSONObject: body); request.timeoutInterval = 3
    URLSession.shared.dataTask(with: request) { _, response, _ in DispatchQueue.main.async { completion((response as? HTTPURLResponse)?.statusCode == 200) } }.resume()
  }
}
