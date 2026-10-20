from pathlib import Path

service_path = Path("app/src/main/kotlin/com/github/digitallyrefined/androidipcamera/StreamingService.kt")
text = service_path.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    text = text.replace(old, new, 1)

replace_once(
    "import kotlinx.coroutines.launch\n",
    "import kotlinx.coroutines.launch\nimport kotlinx.coroutines.runBlocking\n",
    "runBlocking import",
)

replace_once(
    "    var streamingServerHelper: StreamingServerHelper? = null\n",
    "    var streamingServerHelper: StreamingServerHelper? = null\n"
    "    private val serverInitLock = Any()\n"
    "    @Volatile private var certificateGenerationInProgress = false\n"
    "    @Volatile private var serviceShuttingDown = false\n",
    "server lifecycle fields",
)

replace_once(
    '''    private fun handleStopService() {\n        sendBroadcast(Intent("com.github.digitallyrefined.androidipcamera.CLOSE_APP").setPackage(packageName))\n        stopForeground(true); stopSelf()\n    }\n''',
    '''    private fun handleStopService() {\n        serviceShuttingDown = true\n        // Fully release the listener before the Service is allowed to disappear. The server job\n        // runs on its own IO scope, so relying on lifecycle cancellation can leave :4444 alive.\n        runBlocking(Dispatchers.IO) { streamingServerHelper?.stopStreamingServer() }\n        sendBroadcast(Intent("com.github.digitallyrefined.androidipcamera.CLOSE_APP").setPackage(packageName))\n        stopForeground(true); stopSelf()\n    }\n''',
    "handleStopService",
)

old_destroy = '''    override fun onDestroy() {\n        super.onDestroy()\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)\n            try { unregisterReceiver(notificationChannelReceiver) } catch (_: Exception) {}\n        safeStopRecording()\n        // The service is going away, so the torch has nothing left to keep the camera open for;\n        // clearing this first stops the guard in stopCamera() from leaking the session.\n        cameraHeldForTorch = false\n        stopCamera()\n        // A setTorchMode torch outlives the process — release it explicitly or the LED burns\n        // forever after the service is stopped.\n        if (deviceTorchOn) setDeviceTorch(false)\n        lifecycleScope.launch(Dispatchers.IO) { streamingServerHelper?.stopStreamingServer() }\n    }\n'''
new_destroy = '''    override fun onDestroy() {\n        serviceShuttingDown = true\n        // StreamingServerHelper owns an independent IO coroutine. Stop and join it synchronously\n        // before super.onDestroy() cancels LifecycleService's scope; otherwise an orphan listener\n        // can survive this Service instance and make the next one fail with EADDRINUSE.\n        runBlocking(Dispatchers.IO) { streamingServerHelper?.stopStreamingServer() }\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)\n            try { unregisterReceiver(notificationChannelReceiver) } catch (_: Exception) {}\n        safeStopRecording()\n        // The service is going away, so the torch has nothing left to keep the camera open for;\n        // clearing this first stops the guard in stopCamera() from leaking the session.\n        cameraHeldForTorch = false\n        stopCamera()\n        // A setTorchMode torch outlives the process — release it explicitly or the LED burns\n        // forever after the service is stopped.\n        if (deviceTorchOn) setDeviceTorch(false)\n        super.onDestroy()\n    }\n'''
replace_once(old_destroy, new_destroy, "onDestroy")

replace_once(
    '''    fun startStreamingServer() {\n        try {\n''',
    '''    fun startStreamingServer() {\n        if (serviceShuttingDown) return\n        try {\n''',
    "startStreamingServer shutdown guard",
)

old_generate = '''    private fun generateCertificateAndStart() {\n        val pw = generateRandomPassword()\n        lifecycleScope.launch(Dispatchers.IO) {\n            val certFile = CertificateHelper.generateCertificate(this@StreamingService, pw)\n            if (certFile != null) {\n                SecureStorage(this@StreamingService).putSecureString(SecureStorage.KEY_CERT_PASSWORD, pw)\n                PreferenceManager.getDefaultSharedPreferences(this@StreamingService).edit().remove("certificate_path").apply()\n                kotlinx.coroutines.delay(100)\n                initServer()\n            } else launch(Dispatchers.Main) {\n                Toast.makeText(this@StreamingService, "Failed to generate certificate", Toast.LENGTH_LONG).show()\n            }\n        }\n    }\n'''
new_generate = '''    private fun generateCertificateAndStart() {\n        synchronized(serverInitLock) {\n            if (serviceShuttingDown || certificateGenerationInProgress) return\n            certificateGenerationInProgress = true\n        }\n        val pw = generateRandomPassword()\n        lifecycleScope.launch(Dispatchers.IO) {\n            try {\n                val certFile = CertificateHelper.generateCertificate(this@StreamingService, pw)\n                if (certFile != null && !serviceShuttingDown) {\n                    SecureStorage(this@StreamingService).putSecureString(SecureStorage.KEY_CERT_PASSWORD, pw)\n                    PreferenceManager.getDefaultSharedPreferences(this@StreamingService).edit().remove("certificate_path").apply()\n                    kotlinx.coroutines.delay(100)\n                    if (!serviceShuttingDown) initServer()\n                } else if (certFile == null) launch(Dispatchers.Main) {\n                    Toast.makeText(this@StreamingService, "Failed to generate certificate", Toast.LENGTH_LONG).show()\n                }\n            } finally {\n                synchronized(serverInitLock) { certificateGenerationInProgress = false }\n            }\n        }\n    }\n'''
replace_once(old_generate, new_generate, "certificate generation serialization")

replace_once(
    '''    private fun initServer() {\n        if (streamingServerHelper == null) {\n''',
    '''    private fun initServer() {\n        if (serviceShuttingDown) return\n        synchronized(serverInitLock) {\n            if (serviceShuttingDown) return\n            if (streamingServerHelper == null) {\n''',
    "initServer lock open",
)

replace_once(
    '''            mjpegStreamingEncoder = MjpegStreamingEncoder(this, streamingServerHelper!!) { Log.i(TAG, "MJPEG: $it"); onLog?.invoke(it) }\n        }\n        streamingServerHelper?.startStreamingServer()\n    }\n\n    private fun launchMain''',
    '''            mjpegStreamingEncoder = MjpegStreamingEncoder(this, streamingServerHelper!!) { Log.i(TAG, "MJPEG: $it"); onLog?.invoke(it) }\n            }\n            streamingServerHelper?.startStreamingServer()\n        }\n    }\n\n    private fun launchMain''',
    "initServer lock close",
)

service_path.write_text(text)
print("Applied EADDRINUSE v2 lifecycle/init serialization fix")
