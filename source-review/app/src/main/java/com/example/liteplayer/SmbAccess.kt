package com.example.liteplayer

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DataSpec
import jcifs.CIFSContext
import jcifs.context.BaseContext
import jcifs.config.PropertyConfiguration
import java.util.Properties
import jcifs.smb.NtlmPasswordAuthenticator
import jcifs.smb.SmbFile
import jcifs.smb.SmbRandomAccessFile
import java.io.IOException

/**
 * SMB2/3 browsing and random-access streaming. Credentials remain in RAM and
 * are never placed in a URI, intent, log, or preference file.
 */
class SmbAccess(username: String, password: String, domain: String = "", authMode: String = "auto") {
    // jcifs-ng uses distinct authentication types. An ordinary authenticator with
    // empty strings is not the same as an anonymous/null SMB session.
    private val credentials: NtlmPasswordAuthenticator = when {
        authMode == "guest" ->
            NtlmPasswordAuthenticator(NtlmPasswordAuthenticator.AuthenticationType.GUEST)
        authMode == "empty-ntlm" ->
            NtlmPasswordAuthenticator("", "", "")
        authMode == "anonymous" || (username.isBlank() && password.isBlank()) ->
            NtlmPasswordAuthenticator(NtlmPasswordAuthenticator.AuthenticationType.NULL)
        username.equals("guest", ignoreCase = true) && password.isBlank() ->
            NtlmPasswordAuthenticator(NtlmPasswordAuthenticator.AuthenticationType.GUEST)
        else -> {
            val separator = username.indexOf('\\')
            if (separator > 0) {
                NtlmPasswordAuthenticator(username.substring(0, separator),
                    username.substring(separator + 1), password)
            } else NtlmPasswordAuthenticator(domain, username, password)
        }
    }
    // Nova Video Player (Apache-2.0) SMB compatibility settings, adapted
    // from nova-video-player/aos-FileCoreLibrary JcifsUtils.java.
    // Use explicit SMB2/3 negotiation rather than relying on device defaults.
    private val context: CIFSContext = run {
        val props = Properties().apply {
            // Nova normal SMB2 path uses multi-protocol negotiation for
            // server-root share enumeration, not SMB2-only negotiation.
            setProperty("jcifs.smb.client.minVersion", "SMB1")
            setProperty("jcifs.smb.client.maxVersion", "SMB311")
            setProperty("jcifs.smb.client.useSMB2Negotiation", "false")
            setProperty("jcifs.smb.client.dfs.disabled", "true")
            setProperty("jcifs.smb.client.attrExpirationPeriod", "30000")
            // Nova disables enforced signing specifically for the IPC share,
            // allowing compatibility with Windows server enumeration.
            setProperty("jcifs.smb.client.ipcSigningEnforced", "false")
            setProperty("jcifs.smb.client.snd_buf_size", "1048576")
            setProperty("jcifs.smb.client.rcv_buf_size", "1048576")
        }
        val base = BaseContext(PropertyConfiguration(props))
        if (authMode == "nova-guest") base.withGuestCrendentials()
        else base.withCredentials(credentials)
    }

    /** Close this SMB client's transport pool when browsing finishes or fails.
     * Always call off the Android main thread.
     */
    fun disconnect() {
        runCatching { context.close() }
    }

    fun entries(folder: String): List<Pair<String, Boolean>> {
        SmbFile(folder, context).use { directory ->
            // A server root is NOT an ordinary directory. listFiles() followed
            // by isDirectory queries opens extra connections to administrative
            // and IPC shares, which can cause Windows to reject enumeration.
            // Enumerate share NAMES only, without opening each share.
            val path = Uri.parse(folder).path.orEmpty()
            if (path == "/" || path.isEmpty()) {
                return directory.list()
                    .asSequence()
                    .map { it.trimEnd('/') }
                    .filter { it.isNotBlank() && !it.endsWith("$") &&
                              !it.equals("IPC$", ignoreCase = true) }
                    .distinct()
                    .sortedWith(String.CASE_INSENSITIVE_ORDER)
                    .map { it to true }
                    .toList()
            }
            return directory.listFiles()
                .map { child -> child.use { it.name to it.isDirectory } }
                .sortedWith(compareByDescending<Pair<String, Boolean>> { it.second }
                    .thenBy { it.first.lowercase() })
        }
    }

    fun factory(): DataSource.Factory = DataSource.Factory { SmbDataSource(context) }

    private class SmbDataSource(private val context: CIFSContext) : BaseDataSource(true) {
        private var file: SmbRandomAccessFile? = null
        private var openedUri: Uri? = null
        private var left: Long = 0L

        override fun open(dataSpec: DataSpec): Long {
            transferInitializing(dataSpec)
            try {
                val u = dataSpec.uri
                if (u.scheme != "smb") throw IOException("Not an SMB URL")
                val opened = SmbFile(u.toString(), context).openRandomAccess("r")
                try {
                    val length = opened.length()
                    if (dataSpec.position > length) throw IOException("Seek beyond file size")
                    opened.seek(dataSpec.position)
                    file = opened
                    openedUri = u
                    left = if (dataSpec.length == C.LENGTH_UNSET.toLong()) length - dataSpec.position
                           else minOf(dataSpec.length, length - dataSpec.position)
                    transferStarted(dataSpec)
                    return left
                } catch (ex: Exception) {
                    runCatching { opened.close() }
                    throw ex
                }
            } catch (ex: Exception) {
                throw IOException("Unable to open SMB stream", ex)
            }
        }

        override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
            if (length == 0) return 0
            if (left <= 0) return C.RESULT_END_OF_INPUT
            val count = try { file?.read(buffer, offset, minOf(length.toLong(), left).toInt()) }
                        catch (ex: Exception) { throw IOException("SMB read failed", ex) }
                        ?: return C.RESULT_END_OF_INPUT
            if (count < 0) return C.RESULT_END_OF_INPUT
            left -= count
            bytesTransferred(count)
            return count
        }

        override fun getUri(): Uri? = openedUri

        override fun close() {
            val hadFile = file != null
            try { file?.close() } finally {
                file = null
                openedUri = null
                left = 0
                if (hadFile) transferEnded()
            }
        }
    }
}
