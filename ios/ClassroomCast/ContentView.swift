import SwiftUI

struct ContentView: View {
    @State private var client: CastClient?
    @State private var connected = false
    @State private var presetIp: String?
    @State private var presetPort: String?

    var body: some View {
        if connected, let client = client {
            ControlView(client: client) {
                self.client = nil
                self.connected = false
            }
        } else {
            ConnectView(
                presetIp: presetIp,
                presetPort: presetPort,
                onConnected: { c in
                    client = c
                    connected = true
                },
                onScanResult: { ip, port in
                    presetIp = ip
                    presetPort = port
                }
            )
        }
    }
}
