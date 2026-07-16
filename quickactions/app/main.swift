// compress-zip 壳 App：一个后台无 UI 的 App，把"压缩/解压"声明为 macOS 系统服务(NSServices)。
// 系统扫描本 App 的 Info.plist 自动把菜单项登记进访达右键——和 MacZip 同一机制，装完即用、无需手动启用。
// 收到右键服务消息后，从剪贴板取选中文件路径，转手调 ~/tools/compress-zip/ 下的 shell 外壳。
import Cocoa

final class ServiceProvider: NSObject {
    private func runScript(_ script: String, _ pboard: NSPasteboard) {
        let urls = pboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL] ?? []
        let paths = urls.map { $0.path }
        guard !paths.isEmpty else { return }
        let scriptPath = NSHomeDirectory() + "/tools/compress-zip/" + script
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/zsh")
        task.arguments = [scriptPath] + paths   // 选中文件走 argv，脚本自己弹窗交互
        try? task.run()
    }

    @objc func compressZip(_ pboard: NSPasteboard, userData: String?,
                           error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runScript("compress.sh", pboard)
    }
    @objc func decompressZip(_ pboard: NSPasteboard, userData: String?,
                             error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runScript("decompress.sh", pboard)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)          // 后台运行，不占 Dock、无窗口
NSApp.servicesProvider = ServiceProvider()   // 注册服务处理者，系统按需拉起本 App 递消息
app.run()
