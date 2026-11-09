package com.smartpanda.app.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.sceneview.Scene
import io.github.sceneview.math.Position
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberCameraNode
import io.github.sceneview.rememberEngine
import io.github.sceneview.rememberMainLightNode
import io.github.sceneview.rememberModelLoader
import io.github.sceneview.rememberNode
import kotlinx.coroutines.isActive

private const val MODEL_ASSET = "models/panda_rigged.glb"

/** Door/tailgate/window clips baked into panda_rigged.glb (see docs/model_map.md). */
private val DOOR_CLIPS = listOf(
    "door_FL_open" to "Porta ant. SX",
    "door_FR_open" to "Porta ant. DX",
    "door_RL_open" to "Porta post. SX",
    "door_RR_open" to "Porta post. DX",
    "tailgate_open" to "Portellone",
    "window_FL_down" to "Finestrino ant. SX",
    "window_FR_down" to "Finestrino ant. DX",
    "window_RL_down" to "Finestrino post. SX",
    "window_RR_down" to "Finestrino post. DX",
)

/** Looping clip: wheels, body shake and exhaust vibration (see docs/model_map.md). */
private const val RUNNING_CLIP = "running"

/** 1.0 plays the clip at its baked speed, ~26.7 km/h apparent. */
private const val RUNNING_SPEED_SCALE = 1f

/** Lamp materials baked into panda_rigged.glb -> emissive color when on. */
private data class Lamp(val material: String, val label: String, val color: FloatArray)

private val LAMPS = listOf(
    Lamp("mat_headlights", "Fari", floatArrayOf(4f, 4f, 3.4f)),
    Lamp("mat_stoplight", "Stop", floatArrayOf(4f, 0f, 0f)),
    Lamp("mat_foglights", "Fendinebbia", floatArrayOf(3.6f, 3.6f, 4f)),
    Lamp("mat_indicators", "Frecce", floatArrayOf(4f, 2.6f, 0f)),
)

/**
 * Driven, never toggled directly: the front indicator is a corner cut out of
 * the headlamp lens, so while it is not blinking it takes the headlight colour
 * and the lens reads as one piece instead of showing a hole.
 */
private const val INDICATOR_FRONT_MATERIAL = "mat_indicator_front"

/**
 * 3D vehicle status view.
 *
 * For now every door/lamp is driven by the test chips below the scene;
 * in Fase 2 the booleans will come from the CAN middleware instead.
 */
@Composable
fun VehicleScreen(modifier: Modifier = Modifier) {
    val engine = rememberEngine()
    val modelLoader = rememberModelLoader(engine)
    val mainLight = rememberMainLightNode(engine)
    val cameraNode = rememberCameraNode(engine) {
        position = Position(x = 3.2f, y = 1.8f, z = 4.2f)
        lookAt(Position(0f, 0.4f, 0f))
    }
    val modelNode = rememberNode {
        ModelNode(
            modelInstance = modelLoader.createModelInstance(MODEL_ASSET),
            scaleToUnits = 3.4f,
        )
    }

    // --- doors: boolean state -> animated 0..1 progress -> glTF animator time
    val doorOpen = remember { DOOR_CLIPS.associate { (clip, _) -> clip to mutableStateOf(false) } }
    val doorProgress = DOOR_CLIPS.associate { (clip, _) ->
        clip to animateFloatAsState(
            targetValue = if (doorOpen.getValue(clip).value) 1f else 0f,
            animationSpec = tween(durationMillis = 1000),
            label = clip,
        )
    }
    // --- running: looping clip advanced by wall-clock time while the chip is on
    val running = remember { mutableStateOf(false) }

    LaunchedEffect(modelNode) {
        val animator = modelNode.modelInstance.animator
        val indexByName = (0 until animator.animationCount)
            .associateBy { animator.getAnimationName(it) }
        var runningSeconds = 0f
        var lastFrameNanos = 0L
        while (isActive) {
            withFrameNanos { nanos ->
                val delta =
                    if (lastFrameNanos == 0L) 0f
                    else (nanos - lastFrameNanos) / 1_000_000_000f
                lastFrameNanos = nanos

                for ((clip, progress) in doorProgress) {
                    val index = indexByName[clip] ?: continue
                    animator.applyAnimation(
                        index,
                        progress.value * animator.getAnimationDuration(index),
                    )
                }

                indexByName[RUNNING_CLIP]?.let { index ->
                    val duration = animator.getAnimationDuration(index)
                    if (running.value) {
                        runningSeconds =
                            (runningSeconds + delta * RUNNING_SPEED_SCALE) % duration
                        animator.applyAnimation(index, runningSeconds)
                    } else if (runningSeconds != 0f) {
                        // settle back to the rest pose once, then stop touching it
                        runningSeconds = 0f
                        animator.applyAnimation(index, 0f)
                    }
                }

                animator.updateBoneMatrices()
            }
        }
    }

    // --- lamps: boolean state -> emissiveFactor on the dedicated material
    val lampOn = remember { LAMPS.associate { it.material to mutableStateOf(false) } }
    fun setEmissive(material: String, color: FloatArray?) {
        modelNode.modelInstance.materialInstances
            .firstOrNull { it.name == material }
            ?.setParameter(
                "emissiveFactor",
                color?.get(0) ?: 0f,
                color?.get(1) ?: 0f,
                color?.get(2) ?: 0f,
            )
    }

    fun refreshLamps() {
        for (lamp in LAMPS) {
            setEmissive(lamp.material, lamp.color.takeIf { lampOn.getValue(lamp.material).value })
        }
        val indicators = LAMPS.first { it.material == "mat_indicators" }
        val headlights = LAMPS.first { it.material == "mat_headlights" }
        setEmissive(
            INDICATOR_FRONT_MATERIAL,
            when {
                lampOn.getValue(indicators.material).value -> indicators.color
                lampOn.getValue(headlights.material).value -> headlights.color
                else -> null
            },
        )
    }

    Column(modifier = modifier.fillMaxSize()) {
        Scene(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            engine = engine,
            modelLoader = modelLoader,
            cameraNode = cameraNode,
            mainLightNode = mainLight,
            childNodes = listOf(modelNode),
        )
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                var on by running
                FilterChip(
                    selected = on,
                    onClick = { on = !on },
                    label = { Text("In marcia") },
                )
            }
            items(DOOR_CLIPS) { (clip, label) ->
                var open by doorOpen.getValue(clip)
                FilterChip(
                    selected = open,
                    onClick = { open = !open },
                    label = { Text(label) },
                )
            }
            items(LAMPS) { lamp ->
                var on by lampOn.getValue(lamp.material)
                FilterChip(
                    selected = on,
                    onClick = {
                        on = !on
                        refreshLamps()
                    },
                    label = { Text(lamp.label) },
                )
            }
        }
    }
}
