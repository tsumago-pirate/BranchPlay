import Cocoa
import WebKit

/// Transparent panel over the match window. Clicks land here only while the
/// pointer is on a card. Everywhere else they fall through to the game.
final class Bridge: NSObject, WKScriptMessageHandler {
  var rects: [CGRect] = []

  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage
  ) {
    guard let rows = message.body as? [Any] else { return }
    var next: [CGRect] = []
    for row in rows {
      guard let dict = row as? [String: Any] else { continue }
      guard
        let x = (dict["x"] as? NSNumber)?.doubleValue,
        let y = (dict["y"] as? NSNumber)?.doubleValue,
        let w = (dict["w"] as? NSNumber)?.doubleValue,
        let h = (dict["h"] as? NSNumber)?.doubleValue
      else { continue }
      next.append(CGRect(x: x, y: y, width: w, height: h))
    }
    rects = next
  }
}

final class Panel: NSPanel {
  var typing = false
  override var canBecomeKey: Bool { typing }
  override var canBecomeMain: Bool { false }
}

final class Keys: NSObject, WKScriptMessageHandler {
  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage
  ) {
    let on = message.body as? Bool ?? false
    DispatchQueue.main.async {
      setTyping(on)
    }
  }
}

final class Page: WKWebView {
  override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

// A link with the download attribute asks WebKit to save the file.
// https://developer.apple.com/documentation/webkit/wkdownload
final class Downloads: NSObject, WKNavigationDelegate, WKDownloadDelegate {
  func webView(
    _ webView: WKWebView,
    decidePolicyFor navigationAction: WKNavigationAction,
    preferences: WKWebpagePreferences,
    decisionHandler: @escaping (WKNavigationActionPolicy, WKWebpagePreferences) -> Void
  ) {
    if navigationAction.shouldPerformDownload {
      decisionHandler(.download, preferences)
      return
    }
    decisionHandler(.allow, preferences)
  }

  func webView(
    _ webView: WKWebView,
    navigationAction: WKNavigationAction,
    didBecome download: WKDownload
  ) {
    download.delegate = self
  }

  func download(
    _ download: WKDownload,
    decideDestinationUsing response: URLResponse,
    suggestedFilename: String,
    completionHandler: @escaping (URL?) -> Void
  ) {
    DispatchQueue.main.async {
      let wasAccessory = NSApp.activationPolicy() == .accessory
      NSApp.setActivationPolicy(.regular)
      NSApp.activate(ignoringOtherApps: true)
      let save = NSSavePanel()
      save.canCreateDirectories = true
      save.nameFieldStringValue = suggestedFilename.isEmpty ? "branchplay.mp4" : suggestedFilename
      let chosen = save.runModal() == .OK ? save.url : nil
      if wasAccessory {
        NSApp.setActivationPolicy(.accessory)
        if parent > 0 {
          NSRunningApplication(processIdentifier: parent)?.activate(options: [.activateAllWindows])
        }
      }
      completionHandler(chosen)
    }
  }
}

let bridge = Bridge()
let keys = Keys()
let parent = Int32(CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "") ?? 0
let page = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "http://127.0.0.1:8000/"

// Held letters move the camera, and typed fields should not be rewritten.
// These are read when the text system starts, so they are set before the app.
UserDefaults.standard.set(false, forKey: "ApplePressAndHoldEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticSpellingCorrectionEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticTextCompletionEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticTextReplacementEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticQuoteSubstitutionEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticDashSubstitutionEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticCapitalizationEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticPeriodSubstitutionEnabled")
UserDefaults.standard.set(false, forKey: "NSAutomaticInlinePredictionEnabled")
UserDefaults.standard.set(false, forKey: "WebAutomaticSpellingCorrectionEnabled")

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let iconURL = URL(fileURLWithPath: CommandLine.arguments[0])
  .deletingLastPathComponent()
  .appendingPathComponent("brand/branchplay-icon.png")
if let icon = NSImage(contentsOf: iconURL) {
  app.applicationIconImage = icon
}

let panel = Panel(
  contentRect: NSRect(x: 0, y: 0, width: 1280, height: 720),
  styleMask: [.borderless, .nonactivatingPanel],
  backing: .buffered,
  defer: false
)
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.level = .normal
panel.ignoresMouseEvents = true
panel.hidesOnDeactivate = false
// Come to the desktop in front when shown. Joining every desktop is what
// left the menu up on the others.
panel.collectionBehavior = [.fullScreenAuxiliary, .moveToActiveSpace]
panel.isMovable = false
panel.animationBehavior = .none
panel.acceptsMouseMovedEvents = true

let content = panel.contentView!
content.wantsLayer = true
content.layer?.backgroundColor = NSColor.clear.cgColor

let configuration = WKWebViewConfiguration()
configuration.userContentController.add(bridge, name: "hud")
configuration.userContentController.add(keys, name: "type")
// The page's fields would otherwise offer corrections and accent characters.
configuration.userContentController.addUserScript(WKUserScript(
  source: """
  (function () {
    function quiet(node) {
      if (!node || node.nodeType !== 1 || !node.setAttribute) return;
      node.setAttribute("spellcheck", "false");
      node.setAttribute("autocorrect", "off");
      node.setAttribute("autocapitalize", "off");
      node.setAttribute("autocomplete", "off");
      node.setAttribute("writingsuggestions", "false");
      node.spellcheck = false;
    }
    quiet(document.documentElement);
    document.addEventListener("focusin", function (event) { quiet(event.target); }, true);
  })();
  """,
  injectionTime: .atDocumentStart,
  forMainFrameOnly: true
))
let downloads = Downloads()
let web = Page(frame: content.bounds, configuration: configuration)
web.navigationDelegate = downloads
web.autoresizingMask = [.width, .height]
web.setValue(false, forKey: "drawsBackground")
quietTextInput(web)
if #available(macOS 12.0, *) {
  web.underPageBackgroundColor = .clear
}
content.addSubview(web)
web.load(URLRequest(url: URL(string: page)!))

/// Turn off rewriting, completion, and the accent menu on this view. The
/// setters belong to NSTextInputTraits. A view that does not implement one
/// is left alone.
func quietTextInput(_ view: NSView) {
  func setTrait(_ name: String, _ value: Int) {
    let setter = NSSelectorFromString("set\(name):")
    guard view.responds(to: setter) else { return }
    typealias Imp = @convention(c) (AnyObject, Selector, Int) -> Void
    let imp = unsafeBitCast(view.method(for: setter), to: Imp.self)
    imp(view, setter, value)
  }
  // NSTextInputTraitTypeNo, then NSWritingToolsBehaviorNone.
  setTrait("SpellCheckingType", 1)
  setTrait("AutocorrectionType", 1)
  setTrait("GrammarCheckingType", 1)
  setTrait("SmartQuotesType", 1)
  setTrait("SmartDashesType", 1)
  setTrait("TextReplacementType", 1)
  setTrait("TextCompletionType", 1)
  setTrait("InlinePredictionType", 1)
  setTrait("WritingToolsBehavior", -1)
}

func number(_ value: Any?) -> CGFloat? {
  guard let raw = (value as? NSNumber)?.doubleValue else { return nil }
  return CGFloat(raw)
}

func appKitFrame(_ bounds: [String: Any]) -> NSRect? {
  guard
    let x = number(bounds["X"]),
    let y = number(bounds["Y"]),
    let width = number(bounds["Width"]),
    let height = number(bounds["Height"]),
    width > 1, height > 1
  else { return nil }
  // Quartz measures from the top-left of the menu-bar screen. AppKit
  // measures from the bottom-left of that same screen. The first screen
  // in the list is not always that one, so a launch can park the menu
  // off the match until the next open.
  let primary = NSScreen.screens.first(where: { $0.frame.origin == .zero }) ?? NSScreen.screens.first
  let originX = primary?.frame.origin.x ?? 0
  let originY = primary?.frame.origin.y ?? 0
  let screenH = primary?.frame.height ?? height
  return NSRect(
    x: x + originX,
    y: originY + screenH - y - height,
    width: width,
    height: height
  )
}

func windowFrame(of window: [String: Any]) -> (id: CGWindowID, frame: NSRect)? {
  guard let rawID = window[kCGWindowNumber as String] as? NSNumber else { return nil }
  guard let bounds = window[kCGWindowBounds as String] as? [String: Any] else { return nil }
  guard let frame = appKitFrame(bounds) else { return nil }
  return (CGWindowID(rawID.uint32Value), frame)
}

func footballWindow() -> (id: CGWindowID, frame: NSRect)? {
  // On-screen only. A window on another desktop must not pull the panels along.
  let options: CGWindowListOption = [.excludeDesktopElements, .optionOnScreenOnly]
  guard let list = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    return nil
  }
  var owned: (id: CGWindowID, frame: NSRect)?
  var ownedArea: CGFloat = 0
  for window in list {
    guard let found = windowFrame(of: window) else { continue }
    let name = window[kCGWindowName as String] as? String ?? ""
    if name == "BranchPlay Engine" { return found }
    let owner = (window[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value ?? -1
    let area = found.frame.width * found.frame.height
    if parent > 0 && owner == parent && found.frame.height > 400 && area > ownedArea {
      owned = found
      ownedArea = area
    }
  }
  return owned
}

/// The Quartz frame includes the title bar. The page should cover only the
/// picture, so a card at the top of the page sits under that bar. A window
/// that already fills its screen has no bar to skip.
func contentFrame(_ windowFrame: NSRect) -> NSRect {
  let screen = NSScreen.screens.first(where: { $0.frame.intersects(windowFrame) }) ?? NSScreen.main
  if let screen {
    let delta = abs(windowFrame.minX - screen.frame.minX)
      + abs(windowFrame.minY - screen.frame.minY)
      + abs(windowFrame.width - screen.frame.width)
      + abs(windowFrame.height - screen.frame.height)
    if delta < 8 { return windowFrame }
  }
  let title = titleBarHeight
  guard title > 1, title < windowFrame.height else { return windowFrame }
  return NSRect(
    x: windowFrame.minX,
    y: windowFrame.minY,
    width: windowFrame.width,
    height: windowFrame.height - title
  )
}

let titleBarHeight: CGFloat = {
  let sample = NSRect(x: 0, y: 0, width: 800, height: 100)
  let framed = NSWindow.frameRect(
    forContentRect: sample,
    styleMask: [.titled, .closable, .miniaturizable, .resizable]
  )
  return framed.height - sample.height
}()

func moved(_ current: NSRect, _ next: NSRect) -> Bool {
  abs(current.minX - next.minX) >= 0.5 || abs(current.minY - next.minY) >= 0.5
    || abs(current.width - next.width) >= 0.5 || abs(current.height - next.height) >= 0.5
}

func mostlyOnScreen(_ frame: NSRect) -> Bool {
  let area = frame.width * frame.height
  if area <= 1 { return false }
  let visible = NSScreen.screens.reduce(CGFloat(0)) { sum, screen in
    let hit = screen.frame.intersection(frame)
    return sum + max(0, hit.width) * max(0, hit.height)
  }
  // A desktop switch slides the match in from off screen. Ignore that slide.
  return visible > area * 0.6
}

/// True when some other app's window sits over the match. The match process
/// is often not the active app on open, and the menu used to stay behind the
/// picture until a restart made that process active.
func otherAppCovers(_ gameID: CGWindowID, _ gameFrame: NSRect) -> Bool {
  let options: CGWindowListOption = [.excludeDesktopElements, .optionOnScreenOnly]
  guard let list = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    return false
  }
  let overlayPID = ProcessInfo.processInfo.processIdentifier
  let gameArea = max(1, gameFrame.width * gameFrame.height)
  for window in list {
    guard let raw = window[kCGWindowNumber as String] as? NSNumber else { continue }
    let id = CGWindowID(raw.uint32Value)
    if id == gameID { return false }
    if raw.intValue == panel.windowNumber { continue }
    let owner = (window[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value ?? -1
    if owner == overlayPID || (parent > 0 && owner == parent) { continue }
    let layer = (window[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0
    if layer != 0 { continue }
    guard let bounds = window[kCGWindowBounds as String] as? [String: Any] else { continue }
    guard let frame = appKitFrame(bounds) else { continue }
    if frame.width < 40 || frame.height < 40 { continue }
    let hit = frame.intersection(gameFrame)
    if hit.width > 1 && hit.height > 1 && hit.width * hit.height > gameArea * 0.2 {
      return true
    }
  }
  return false
}

/// Front-to-back. True when the match window is listed before this panel,
/// which is what a click on the picture does: it raises the match and the
/// menu vanishes until something orders the panel forward again.
func gameCoversPanel(_ gameID: CGWindowID) -> Bool {
  let options: CGWindowListOption = [.excludeDesktopElements, .optionOnScreenOnly]
  guard let list = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    return false
  }
  for window in list {
    guard let raw = window[kCGWindowNumber as String] as? NSNumber else { continue }
    if raw.intValue == panel.windowNumber { return false }
    if CGWindowID(raw.uint32Value) == gameID { return true }
  }
  return false
}

var unseenSince: CFAbsoluteTime?
var dropAboveAt: CFAbsoluteTime?
var pageReady = false
var settledFrame = NSRect.zero
var settledAt = CFAbsoluteTime(0)

/// The desktop switch slides the match in from off screen. Placing the menu
/// on that passing frame leaves it beside the picture.
func windowSettled(_ frame: NSRect) -> Bool {
  let now = CFAbsoluteTimeGetCurrent()
  if moved(settledFrame, frame) {
    settledFrame = frame
    settledAt = now
    return false
  }
  return now - settledAt >= 0.2
}

/// The page loads while this panel is hidden. WebKit can keep a clear layer,
/// and freezing redraws would leave that blank menu on the picture.
func wakePage() {
  if pageReady { return }
  let frame = web.frame
  guard frame.width > 1, frame.height > 1 else { return }
  web.layerContentsRedrawPolicy = .duringViewResize
  content.layerContentsRedrawPolicy = .duringViewResize
  web.setFrameSize(NSSize(width: frame.width, height: max(1, frame.height - 1)))
  web.layoutSubtreeIfNeeded()
  web.setFrameSize(frame.size)
  web.layoutSubtreeIfNeeded()
  pageReady = true
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
    web.layerContentsRedrawPolicy = .never
    content.layerContentsRedrawPolicy = .never
  }
}

func track() {
  if parent > 0 && kill(parent, 0) != 0 {
    app.terminate(nil)
    return
  }
  guard let game = footballWindow(), mostlyOnScreen(game.frame) else {
    // One missed window-list sample used to hide the menu immediately.
    // A branch runs on the match thread and the window list can miss for
    // a moment. Hiding here is what takes the page off the picture.
    let now = CFAbsoluteTimeGetCurrent()
    if unseenSince == nil { unseenSince = now }
    if let since = unseenSince, now - since > 2.0, panel.isVisible {
      panel.orderOut(nil)
    }
    return
  }
  unseenSince = nil
  // The first show waits until the match has stopped moving. After that, a
  // drag still moves the menu with the window.
  if !panel.isVisible && !windowSettled(game.frame) {
    return
  }
  let frame = contentFrame(game.frame)
  let fullscreen = frame.equalTo(game.frame)
  // The timeline is a band inside the match window. This panel stays on
  // that window and does not hang below it. A titled window's bottom
  // corners are a 12pt continuous curve. This panel is its own rectangle,
  // so the same curve has to clip it or the band draws outside the window.
  let panelFrame = frame
  let radius: CGFloat = fullscreen ? 0 : 12
  if content.layer?.cornerRadius != radius {
    if #available(macOS 12.0, *) {
      content.layer?.cornerCurve = .continuous
    }
    content.layer?.cornerRadius = radius
    content.layer?.maskedCorners = [.layerMinXMinYCorner, .layerMaxXMinYCorner]
    content.layer?.masksToBounds = radius > 0
  }
  // A pitch click raises the match window. At the same level that covers
  // this panel, and ordering it forward again flashes the cards. Stay above
  // the match while that app is the one in front.
  let processFront = parent <= 0 || NSRunningApplication(processIdentifier: parent)?.isActive == true
  let covered = otherAppCovers(game.id, game.frame)
  let now = CFAbsoluteTimeGetCurrent()
  if !covered || processFront || fullscreen || panel.typing {
    dropAboveAt = nil
  } else if dropAboveAt == nil {
    dropAboveAt = now + 0.25
  }
  let holding = dropAboveAt != nil && now < (dropAboveAt ?? now)
  let aboveGame = fullscreen || processFront || panel.typing || !covered || holding
  let level: NSWindow.Level = aboveGame ? .floating : .normal
  let levelChanged = panel.level != level
  if levelChanged { panel.level = level }
  let sizeChanged = abs(panel.frame.width - panelFrame.width) >= 0.5
    || abs(panel.frame.height - panelFrame.height) >= 0.5
  // Place the panel on the match before it is shown, so it does not appear
  // somewhere else and travel over.
  if sizeChanged {
    panel.setFrame(panelFrame, display: true, animate: false)
  } else if moved(panel.frame, panelFrame) {
    panel.setFrameOrigin(panelFrame.origin)
  }
  if !panel.isVisible || levelChanged {
    // Ordering against the match window can pull this panel down into that
    // window's level. Come forward inside this level instead.
    panel.orderFrontRegardless()
    wakePage()
  } else if panel.isVisible && !pageReady {
    wakePage()
  } else if !aboveGame && gameCoversPanel(game.id) {
    panel.order(.above, relativeTo: Int(game.id))
  }
  let mouse = NSEvent.mouseLocation
  let localX = panelFrame.width > 0 ? (mouse.x - panelFrame.minX) / panelFrame.width : 0
  let localY = panelFrame.height > 0 ? (panelFrame.maxY - mouse.y) / panelFrame.height : 0
  var hit = false
  for rect in bridge.rects {
    if localX >= rect.minX && localX <= rect.maxX && localY >= rect.minY && localY <= rect.maxY {
      hit = true
      break
    }
  }
  panel.ignoresMouseEvents = !hit
  // The field only keeps the keyboard while the pointer is on this card.
  // A click on the pitch has to reach the match, keys included.
  if panel.typing && !hit {
    setTyping(false)
  }
}

func setTyping(_ on: Bool) {
  if panel.typing == on { return }
  panel.typing = on
  if on {
    NSApp.setActivationPolicy(.regular)
    NSApp.activate(ignoringOtherApps: true)
    panel.makeKey()
    return
  }
  panel.resignKey()
  web.evaluateJavaScript("document.activeElement && document.activeElement.blur()", completionHandler: nil)
  NSApp.setActivationPolicy(.accessory)
  if parent > 0 {
    NSRunningApplication(processIdentifier: parent)?.activate(options: [.activateAllWindows])
  }
}

// A display link pauses once the panel hides, which is what dropped the
// panels when the match window was not ready on the first look. This timer
// keeps looking, including while the panel is hidden.
let timer = Timer(timeInterval: 1.0 / 120.0, repeats: true) { _ in track() }
timer.tolerance = 0
RunLoop.main.add(timer, forMode: .common)
track()
app.run()
