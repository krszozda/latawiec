package io.github.krszozda.latawiec

import android.content.Context
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.yandex.div.core.player.DivPlayer
import com.yandex.div.core.player.DivPlayerFactory
import com.yandex.div.core.player.DivPlayerPlaybackConfig
import com.yandex.div.core.player.DivPlayerView
import com.yandex.div.core.player.DivVideoSource

/**
 * The opt-in player: ExoPlayer plays DASH and adaptive HLS, which the
 * platform player does not, at the cost of about 726 KiB — more than the
 * whole APK budget has left — so it exists only in a `-PwithVideo` build.
 * [SystemPlayerFactory] stays the default and the shell picks between them
 * at runtime.
 *
 * Like the platform player it ignores scale and never reports elapsed
 * time, so `elapsed_time_variable` stays inert; neither is reachable from
 * the Python DSL.
 */
class Media3PlayerFactory(private val context: Context) : DivPlayerFactory {

    override fun makePlayer(
        src: List<DivVideoSource>,
        config: DivPlayerPlaybackConfig,
    ): DivPlayer = Media3Player(context, src, config)

    override fun makePlayerView(context: Context): DivPlayerView = Media3PlayerView(context)
}

class Media3Player(
    context: Context,
    sources: List<DivVideoSource>,
    config: DivPlayerPlaybackConfig,
) : DivPlayer, HoldablePlayer {

    private val observers = mutableSetOf<DivPlayer.Observer>()

    /** What to go back to once the screen on top of this one is gone. */
    private var playingWhenHeld = false

    internal val exo: ExoPlayer = ExoPlayer.Builder(context).build().apply {
        addListener(
            object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    when (state) {
                        Player.STATE_READY -> notify(DivPlayer.Observer::onReady)
                        Player.STATE_ENDED -> notify(DivPlayer.Observer::onEnd)
                        Player.STATE_BUFFERING -> notify(DivPlayer.Observer::onBuffering)
                        else -> Unit
                    }
                }

                override fun onPlayerError(error: PlaybackException) {
                    // Without this a bad URL is a silent 200 dp band: the
                    // preview image only hides on onReady, which never comes.
                    notify { it.onFatal(error) }
                }

                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    notify { if (isPlaying) it.onPlay() else it.onPause() }
                }
            },
        )
    }

    init {
        apply(sources, config)
    }

    /** An observer may unregister from inside its callback. */
    private fun notify(event: (DivPlayer.Observer) -> Unit) {
        observers.toList().forEach(event)
    }

    override fun hold() {
        playingWhenHeld = exo.isPlaying
        exo.pause()
    }

    override fun resume() {
        if (playingWhenHeld) exo.play()
    }

    private fun apply(sources: List<DivVideoSource>, config: DivPlayerPlaybackConfig) {
        exo.repeatMode =
            if (config.repeatable) Player.REPEAT_MODE_ONE else Player.REPEAT_MODE_OFF
        exo.volume = if (config.isMuted) DivPlayer.VOLUME_MUTED else DivPlayer.VOLUME_FULL
        // DivKit lists its sources best-first and ExoPlayer reads the
        // format from the URL, so the first one it can open wins.
        sources.firstOrNull()?.let { exo.setMediaItem(MediaItem.fromUri(it.url.toString())) }
        exo.prepare()
        exo.playWhenReady = config.autoplay
    }

    override fun play() {
        exo.play()
    }

    override fun pause() {
        exo.pause()
    }

    override fun seek(toMs: Long) {
        exo.seekTo(toMs)
    }

    override fun release() {
        exo.release()
    }

    override fun setMuted(muted: Boolean) {
        exo.volume = if (muted) DivPlayer.VOLUME_MUTED else DivPlayer.VOLUME_FULL
    }

    override fun setPlaybackSpeed(speed: Float) {
        exo.setPlaybackSpeed(speed)
    }

    override fun setSource(
        sourceVariants: List<DivVideoSource>,
        config: DivPlayerPlaybackConfig,
    ) {
        // DivKit calls this when the source or the settings actually
        // changed, so this is a different video: carrying the old one's
        // position across would start it in the middle.
        apply(sourceVariants, config)
    }

    override fun addObserver(observer: DivPlayer.Observer) {
        observers.add(observer)
    }

    override fun removeObserver(observer: DivPlayer.Observer) {
        observers.remove(observer)
    }
}

class Media3PlayerView(context: Context) : DivPlayerView(context) {

    private val surface = PlayerView(context).apply {
        // The shell draws its own chrome from the server's screen; the
        // player's own controls are not part of that.
        useController = false
    }
    private var player: Media3Player? = null

    init {
        addView(surface, LayoutParams(MATCH_PARENT, MATCH_PARENT, Gravity.CENTER))
    }

    override fun attach(player: DivPlayer) {
        detach()
        val media3 = player as? Media3Player ?: return
        this.player = media3
        surface.player = media3.exo
    }

    override fun detach() {
        surface.player = null
        player = null
    }

    override fun getAttachedPlayer(): DivPlayer? = player
}
