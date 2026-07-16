// compress-zip 壳 App：一个后台无 UI 的 App，把"压缩/解压"声明为 macOS 系统服务(NSServices)。
// 系统扫描本 App 的 Info.plist 自动把菜单项登记进访达右键——和 MacZip 同一机制，装完即用、无需手动启用。
// 收到右键服务消息后，从剪贴板取选中文件路径，转手调 ~/tools/compress-zip/ 下的 shell 外壳。
import Cocoa

final class ServiceProvider: NSObject {
    // 统一入口：按 mode 调 czip-menu.sh（zip/compress/here/to），选中文件走 argv。
    private func runMode(_ mode: String, _ pboard: NSPasteboard) {
        let urls = pboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL] ?? []
        let paths = urls.map { $0.path }
        guard !paths.isEmpty else { return }
        let scriptPath = NSHomeDirectory() + "/tools/compress-zip/czip-menu.sh"
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/zsh")
        task.arguments = [scriptPath, mode] + paths
        do { try task.run() }                     // 别静默吞错：脚本缺失/无权限时留日志可查
        catch { NSLog("compress-zip: 无法启动 %@ (%@): %@", scriptPath, mode, error.localizedDescription) }
    }

    // 消息名保持不变（compressZip/decompressZip），用户已绑的快捷键不受影响。
    @objc func compressZip(_ pboard: NSPasteboard, userData: String?,
                           error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runMode("zip", pboard)          // 一键 zip、不加密
    }
    @objc func compressMore(_ pboard: NSPasteboard, userData: String?,
                            error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runMode("compress", pboard)     // 选 7z/tar.gz + 加密 + 密码
    }
    @objc func decompressZip(_ pboard: NSPasteboard, userData: String?,
                             error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runMode("here", pboard)         // 解压到此处，加密包才问密码
    }
    @objc func decompressTo(_ pboard: NSPasteboard, userData: String?,
                            error: AutoreleasingUnsafeMutablePointer<NSString>?) {
        runMode("to", pboard)           // 解压到指定文件夹
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)          // 后台运行，不占 Dock、无窗口
NSApp.servicesProvider = ServiceProvider()   // 注册服务处理者，系统按需拉起本 App 递消息
app.run()
