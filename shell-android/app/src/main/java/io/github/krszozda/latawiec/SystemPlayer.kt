package io.github.krszozda.latawiec

import android.content.Context
import android.media.MediaPlayer
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.VideoView
import com.yandex.div.core.player.DivPlayer
import com.yandex.div.core.player.DivPlayerFactory
import com.yandex.div.core.player.DivPlayerPlaybackConfig
import com.yandex.div.core.player.DivPlayerView
import com.yandex.div.core.player.DivVideoSource

/**
 * A zero-dependency DivKit player on the platform MediaPlayer: it plays
 * what the system plays (MP4, HLS) and keeps the clean shell inside its
 * size budget. An app that needs DASH or DRM swaps in a Media3-backed
 * factory instead of growing everyone's APK.
 */
class SystemPlayerFactory : DivPlayerFactory {

    override fun makePlayer(
        src: List<DivVideoSource>,
        config: DivPlayerPlaybackConfig,
    ): DivPlayer = SystemPlayer(src, config)

    override fun makePlayerView(context: Context): DivPlayerView = SystemPlayerView(context)
}

/**
 * Deliberately minimal: onBuffering/onCurrentTimeChange are never emitted
 * (so elapsed_time_variable and buffering actions stay inert), playback
 * speed is ignored, and scale always letterboxes — none of these are
 * reachable from the Python DSL today.
 */
class SystemPlayer(
    private var sources: List<DivVideoSource>,
    private var config: DivPlayerPlaybackConfig,
) : DivPlayer, HoldablePlayer {

    private val observers = mutableSetOf<DivPlayer.Observer>()
    private var video: VideoView? = null
    private var media: MediaPlayer? = null
    private var muted = false
    private var prepared = false
    private var playWhenReady = false

    /** The view half calls this when DivKit attaches player to surface. */
    fun bind(view: VideoView) {
        video = view
        // setVideoURI releases the previous MediaPlayer; touching the old
        // reference afterwards would throw.
        media = null
        prepared = false
        val url = sources.firstOrNull()?.url
        if (url == null) {
            view.stopPlayback()
            return
        }
        muted = config.isMuted
        playWhenReady = config.autoplay
        view.setOnPreparedListener { player ->
            media = player
            player.isLooping = config.repeatable
            applyVolume()
            prepared = true
            notify(DivPlayer.Observer::onReady)
            if (playWhenReady) {
                view.start()
                notify(DivPlayer.Observer::onPlay)
            }
        }
        view.setOnCompletionListener { notify(DivPlayer.Observer::onEnd) }
        view.setOnErrorListener { _, _, _ ->
            notify(DivPlayer.Observer::onFatal)
            true
        }
        view.setVideoURI(url)
    }

    fun unbind() {
        video?.stopPlayback()
        video = null
        media = null
        prepared = false
    }

    /** Covered by another screen: stop decoding but keep the intent. */
    override fun hold() {
        if (prepared) video?.pause()
    }

    /** Uncovered again: pick up where the intent left off. */
    override fun resume() {
        if (prepared && playWhenReady) video?.start()
    }

    /** An observer may unregister from inside its callback. */
    private fun notify(event: (DivPlayer.Observer) -> Unit) {
        observers.toList().forEach(event)
    }

    private fun applyVolume() {
        val volume = if (muted) 0f else 1f
        try {
            media?.setVolume(volume, volume)
        } catch (e: IllegalStateException) {
            // The surface died and took the MediaPlayer with it.
            media = null
        }
    }

    override fun play() {
        playWhenReady = true
        if (prepared) {
            video?.start()
            notify(DivPlayer.Observer::onPlay)
        }
    }

    override fun pause() {
        playWhenReady = false
        if (prepared) {
            video?.pause()
            notify(DivPlayer.Observer::onPause)
        }
    }

    override fun seek(to: Long) {
        video?.seekTo(to.toInt())
    }

    override fun setMuted(muted: Boolean) {
        this.muted = muted
        applyVolume()
    }

    override fun setSource(src: List<DivVideoSource>, config: DivPlayerPlaybackConfig) {
        sources = src
        this.config = config
        video?.let(::bind)
    }

    override fun addObserver(observer: DivPlayer.Observer) {
        observers.add(observer)
    }

    override fun removeObserver(observer: DivPlayer.Observer) {
        observers.remove(observer)
    }

    override fun release() {
        unbind()
        observers.clear()
    }
}

class SystemPlayerView(context: Context) : DivPlayerView(context) {

    private val video = VideoView(context)
    private var player: SystemPlayer? = null

    init {
        addView(video, LayoutParams(MATCH_PARENT, MATCH_PARENT, Gravity.CENTER))
    }

    override fun attach(player: DivPlayer) {
        detach()
        val system = player as? SystemPlayer ?: return
        this.player = system
        system.bind(video)
    }

    override fun detach() {
        player?.unbind()
        player = null
    }

    override fun getAttachedPlayer(): DivPlayer? = player
}
