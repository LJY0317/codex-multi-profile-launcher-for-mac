import AppKit
import Foundation

@main
final class CodexWebGPTMenu: NSObject, NSApplicationDelegate {
  private let home = FileManager.default.homeDirectoryForCurrentUser
  private var statusItem: NSStatusItem!
  private var statuses = [1: "확인 중", 2: "확인 중"]
  private var refreshTimer: Timer?

  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.setActivationPolicy(.accessory)
    statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    statusItem.button?.title = "Codex"
    refreshMenu()
    refreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
      self?.refreshBridgeStatus()
    }
    refreshBridgeStatus()
  }

  func applicationWillTerminate(_ notification: Notification) {
    refreshTimer?.invalidate()
  }

  private func wrapper(_ name: String) -> URL {
    home.appendingPathComponent("Applications/\(name).app")
  }

  @objc private func openChatGPT1() { open(wrapper("ChatGPT (1)")) }
  @objc private func openChatGPT2() { open(wrapper("ChatGPT (2)")) }
  @objc private func openBridge1() { open(wrapper("Codex Web GPT (1)")) }
  @objc private func openBridge2() { open(wrapper("Codex Web GPT (2)")) }

  private func open(_ url: URL) {
    guard FileManager.default.fileExists(atPath: url.path) else { return }
    NSWorkspace.shared.open(url)
  }

  private func accountMenu(_ account: Int) -> NSMenuItem {
    let item = NSMenuItem(title: "Account \(account) — \(statuses[account] ?? "확인 불가")", action: nil, keyEquivalent: "")
    let submenu = NSMenu(title: "Account \(account)")
    submenu.addItem(actionItem("ChatGPT (\(account)) 열기", account == 1 ? #selector(openChatGPT1) : #selector(openChatGPT2)))
    submenu.addItem(actionItem("브리지 런처 (\(account)) 열기", account == 1 ? #selector(openBridge1) : #selector(openBridge2)))
    submenu.addItem(.separator())
    submenu.addItem(NSMenuItem(title: "승인 요청: 브리지 연결 후 표시", action: nil, keyEquivalent: ""))
    submenu.addItem(NSMenuItem(title: "브리지 시작 / 종료: 브리지 연결 후 표시", action: nil, keyEquivalent: ""))
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
    menu.addItem(accountMenu(1))
    menu.addItem(accountMenu(2))
    menu.addItem(.separator())
    menu.addItem(NSMenuItem(title: "공통 설정", action: nil, keyEquivalent: ""))
    menu.addItem(NSMenuItem(title: "로그인 시 메뉴 실행", action: nil, keyEquivalent: ""))
    menu.addItem(NSMenuItem(title: "로그인 시 Account 1 브리지 실행", action: nil, keyEquivalent: ""))
    menu.addItem(NSMenuItem(title: "로그인 시 Account 2 브리지 실행", action: nil, keyEquivalent: ""))
    menu.addItem(.separator())
    menu.addItem(actionItem("메뉴 앱 종료 — 브리지와 ChatGPT는 유지", #selector(quitMenuOnly)))
    statusItem.menu = menu
    statusItem.button?.title = statuses.values.contains(where: { $0.contains("승인") }) ? "! Codex" : "Codex"
  }

  @objc private func quitMenuOnly() { NSApp.terminate(nil) }

  private func refreshBridgeStatus() {
    for (account, port) in [1: 17842, 2: 17841] {
      guard let url = URL(string: "http://127.0.0.1:\(port)/healthz") else { continue }
      var request = URLRequest(url: url)
      request.timeoutInterval = 2
      URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
        let next: String
        if let data,
           let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           object["status"] as? String == "ok" {
          next = "연결됨"
        } else if response == nil {
          next = "종료 또는 확인 불가"
        } else {
          next = "연결 불가"
        }
        DispatchQueue.main.async {
          self?.statuses[account] = next
          self?.refreshMenu()
        }
      }.resume()
    }
  }
}
