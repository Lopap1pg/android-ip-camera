#!/usr/bin/env python3
from pathlib import Path

HELPER = Path("app/src/main/kotlin/com/github/digitallyrefined/androidipcamera/helpers/StreamingServerHelper.kt")
SERVICE = Path("app/src/main/kotlin/com/github/digitallyrefined/androidipcamera/StreamingService.kt")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


helper = HELPER.read_text(encoding="utf-8")

if "import java.net.InetSocketAddress\n" not in helper:
    helper = replace_once(
        helper,
        "import java.net.InetAddress\n",
        "import java.net.InetAddress\nimport java.net.InetSocketAddress\n",
        "InetSocketAddress import",
    )

helper = replace_once(
    helper,
    '''                                              sslServerSocket = (sslServerSocketFactory.createServerSocket(port, 50, bindAddress) as SSLServerSocket).apply {
                                                  reuseAddress = true
                                                  enabledProtocols = arrayOf(tlsVersion)
                                                  // Don't restrict cipher suites - let the system negotiate
                                                  soTimeout = 30000
                                              }
''',
    '''                                              // createServerSocket(port, ...) binds before the apply block runs,
                                              // which makes reuseAddress too late to help with rapid restarts.
                                              // Create an unbound socket, set SO_REUSEADDR first, then bind.
                                              sslServerSocket = (sslServerSocketFactory.createServerSocket() as SSLServerSocket).apply {
                                                  reuseAddress = true
                                                  bind(InetSocketAddress(bindAddress, port), 50)
                                                  enabledProtocols = arrayOf(tlsVersion)
                                                  // Don't restrict cipher suites - let the system negotiate
                                                  soTimeout = 30000
                                              }
''',
    "TLS bind",
)

helper = replace_once(
    helper,
    '''                                  httpSocket = ServerSocket(port, 50, bindAddress).apply {
                                      reuseAddress = true
                                      soTimeout = 30000
                                  }
''',
    '''                                  // Configure SO_REUSEADDR before bind for the same reason as TLS above.
                                  httpSocket = ServerSocket().apply {
                                      reuseAddress = true
                                      bind(InetSocketAddress(bindAddress, port), 50)
                                      soTimeout = 30000
                                  }
''',
    "HTTP bind",
)

helper = replace_once(
    helper,
    '''                      } catch (keystoreException: Exception) {
                          Handler(Looper.getMainLooper()).post {
                              onLog("Certificate loading failed: ${keystoreException.message}")
                              val errorMsg = when {
                                  keystoreException.message?.contains("password") == true ->
                                      "Certificate password is incorrect, check Settings > Advanced Security"
                                  keystoreException.message?.contains("keystore") == true ->
                                      "Certificate file is corrupted or invalid, regenerate with setup.bat"
                                  else ->
                                      "Certificate error: ${keystoreException.message}"
                              }
                              Toast.makeText(context, errorMsg, Toast.LENGTH_LONG).show()
                          }
                          return@launch
                      }
''',
    '''                      } catch (keystoreException: Exception) {
                          Handler(Looper.getMainLooper()).post {
                              val message = keystoreException.message ?: "Unknown error"
                              val isBindError = message.contains("Address already in use") ||
                                  message.contains("BindException") ||
                                  message.contains("errno = 48") ||
                                  message.contains("EADDRINUSE")
                              if (isBindError) {
                                  onLog("HTTPS bind failed on port $port: $message")
                              } else {
                                  onLog("Certificate loading failed: $message")
                              }
                              val errorMsg = when {
                                  isBindError ->
                                      "Failed to start HTTPS server: port $port is already in use"
                                  message.contains("password") ->
                                      "Certificate password is incorrect, check Settings > Advanced Security"
                                  message.contains("keystore") ->
                                      "Certificate file is corrupted or invalid, regenerate with setup.bat"
                                  else ->
                                      "Certificate error: $message"
                              }
                              Toast.makeText(context, errorMsg, Toast.LENGTH_LONG).show()
                          }
                          return@launch
                      }
''',
    "TLS error classification",
)

HELPER.write_text(helper, encoding="utf-8")

service = SERVICE.read_text(encoding="utf-8")
service = replace_once(
    service,
    '''        lifecycleScope.launch(Dispatchers.IO) {
            streamingServerHelper?.stopServer()
            kotlinx.coroutines.delay(500)
            streamingServerHelper?.startStreamingServer()
        }
''',
    '''        lifecycleScope.launch(Dispatchers.IO) {
            // Wait until accept() has been interrupted and the old server coroutine has fully
            // unwound before binding a replacement listener. stopServer() cleared the shared
            // references immediately, which allowed a second listener to race the first one.
            streamingServerHelper?.stopStreamingServer()
            streamingServerHelper?.startStreamingServer()
        }
''',
    "restartServer shutdown",
)
SERVICE.write_text(service, encoding="utf-8")

print("Applied EADDRINUSE restart/bind fix successfully")
