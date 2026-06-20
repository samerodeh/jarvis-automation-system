import SwiftUI

struct Message: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
}

@MainActor
class JarvisViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var input = ""
    @Published var macIP: String = UserDefaults.standard.string(forKey: "macIP") ?? ""
    @Published var isSending = false
    @Published var showIPSheet = false

    var url: URL? {
        guard !macIP.isEmpty else { return nil }
        return URL(string: "http://\(macIP):8765/ask")
    }

    func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let url else { return }
        input = ""
        messages.append(Message(text: text, isUser: true))
        isSending = true

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])
        req.timeoutInterval = 30

        Task {
            do {
                let (data, _) = try await URLSession.shared.data(for: req)
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: String],
                   let reply = json["reply"] {
                    messages.append(Message(text: reply, isUser: false))
                } else {
                    messages.append(Message(text: "No response from Jarvis.", isUser: false))
                }
            } catch {
                messages.append(Message(text: "Error: \(error.localizedDescription)", isUser: false))
            }
            isSending = false
        }
    }

    func saveIP() {
        UserDefaults.standard.set(macIP, forKey: "macIP")
    }
}

struct ContentView: View {
    @StateObject private var vm = JarvisViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(vm.messages) { msg in
                                MessageBubble(message: msg)
                                    .id(msg.id)
                            }
                            if vm.isSending {
                                HStack(spacing: 6) {
                                    ProgressView()
                                    Text("Thinking…")
                                        .foregroundStyle(.secondary)
                                        .font(.subheadline)
                                }
                                .padding(.horizontal)
                                .id("spinner")
                            }
                        }
                        .padding()
                    }
                    .onChange(of: vm.messages.count) { _, _ in
                        if let last = vm.messages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                    .onChange(of: vm.isSending) { _, sending in
                        if sending {
                            withAnimation { proxy.scrollTo("spinner", anchor: .bottom) }
                        }
                    }
                }

                Divider()

                HStack(alignment: .bottom, spacing: 8) {
                    TextField("Message Jarvis…", text: $vm.input, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .lineLimit(1...5)

                    Button(action: vm.send) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                            .foregroundStyle(canSend ? .blue : .gray)
                    }
                    .disabled(!canSend)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
            .navigationTitle("Jarvis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        vm.showIPSheet = true
                    } label: {
                        Image(systemName: "network")
                    }
                }
            }
            .sheet(isPresented: $vm.showIPSheet) {
                IPSettingsView(vm: vm)
            }
            .onAppear {
                if vm.macIP.isEmpty { vm.showIPSheet = true }
            }
        }
    }

    private var canSend: Bool {
        !vm.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !vm.isSending
            && vm.url != nil
    }
}

struct MessageBubble: View {
    let message: Message

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }
            Text(message.text)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(message.isUser ? Color.blue : Color(.systemGray5))
                .foregroundStyle(message.isUser ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            if !message.isUser { Spacer(minLength: 60) }
        }
    }
}

struct IPSettingsView: View {
    @ObservedObject var vm: JarvisViewModel
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Mac's local IP address") {
                    TextField("e.g. 192.168.1.42", text: $vm.macIP)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }
                Section {
                    Text("Mac and iPhone must be on the same Wi-Fi network.\n\nFind your Mac's IP: System Settings → Wi-Fi → tap the network name → IP Address.")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }
            }
            .navigationTitle("Mac Connection")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        vm.saveIP()
                        dismiss()
                    }
                }
            }
        }
    }
}
