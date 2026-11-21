package com.example.liteplayer

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DataSpec
import jcifs.CIFSContext
import jcifs.context.SingletonContext
import jcifs.smb.NtlmPasswordAuthenticator
import jcifs.smb.SmbFile
import jcifs.smb.SmbRandomAccessFile
import java.io.IOException

/**
 * SMB2/3 browsing and random-access streaming. Credentials remain in RAM and
 * are never placed in a URI, intent, log, or preference file.
 */
class SmbAccess(username: String, password: String, domain: String = "") {
    private val context: CIFSContext = SingletonContext.getInstance()
        .withCredentials(NtlmPasswordAuthenticator(domain, username, password))

    fun entries(folder: String): List<Pair<String, Boolean>> {
        SmbFile(folder, context).use { directory ->
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
                val opened = SmbRandomAccessFile(SmbFile(u.toString(), context), "r")
                val length = opened.length()
                if (dataSpec.position > length) {
                    opened.close()
                    throw IOException("Seek beyond file size")
                }
                opened.seek(dataSpec.position)
                file = opened
                openedUri = u
                left = if (dataSpec.length == C.LENGTH_UNSET.toLong()) length - dataSpec.position
                       else minOf(dataSpec.length, length - dataSpec.position)
                transferStarted(dataSpec)
                return left
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
