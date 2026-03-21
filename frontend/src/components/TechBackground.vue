<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

type NodePoint = {
    x: number;
    y: number;
    vx: number;
    vy: number;
    phase: number;
};

const canvasRef = ref<HTMLCanvasElement | null>(null);

let ctx: CanvasRenderingContext2D | null = null;
let rafId = 0;
let nodes: NodePoint[] = [];
let width = 0;
let height = 0;
let dpr = 1;
let lastFrameTime = 0;

const pointer = {
    x: -10_000,
    y: -10_000,
    active: false,
};

const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function random(min: number, max: number): number {
    return min + Math.random() * (max - min);
}

function createNodes(): NodePoint[] {
    const area = width * height;
    const targetCount = Math.max(36, Math.min(120, Math.floor(area / 30_000)));
    const generated: NodePoint[] = [];
    for (let i = 0; i < targetCount; i += 1) {
        generated.push({
            x: random(0, width),
            y: random(0, height),
            vx: random(-0.07, 0.07),
            vy: random(-0.07, 0.07),
            phase: random(0, Math.PI * 2),
        });
    }
    return generated;
}

function resizeCanvas() {
    const canvas = canvasRef.value;
    if (!canvas) return;

    width = window.innerWidth;
    height = window.innerHeight;
    dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    nodes = createNodes();
}

function drawWaveGrid(timeMs: number) {
    if (!ctx) return;

    const grid = Math.max(36, Math.min(56, Math.floor(width / 28)));
    const amplitudeBase = Math.max(5, Math.min(16, width / 120));
    const time = timeMs * 0.0005;

    ctx.save();
    ctx.strokeStyle = "rgba(125, 211, 252, 0.20)";
    ctx.lineWidth = 1;

    for (let y = -grid; y < height + grid; y += grid) {
        ctx.beginPath();
        for (let x = 0; x <= width; x += 12) {
            const dx = x - pointer.x;
            const dy = y - pointer.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const pointerInfluence = pointer.active
                ? Math.max(0, 1 - dist / 260)
                : 0;
            const amp = amplitudeBase + pointerInfluence * 18;
            const wave =
                Math.sin(x * 0.02 + time + y * 0.004) * amp +
                Math.cos(x * 0.012 - time * 1.1) * amp * 0.33;
            const py = y + wave;
            if (x === 0) ctx.moveTo(x, py);
            else ctx.lineTo(x, py);
        }
        ctx.stroke();
    }

    ctx.restore();
}

function updateAndDrawNodes(timeMs: number) {
    if (!ctx) return;

    const time = timeMs * 0.001;
    const linkDistance = Math.max(120, Math.min(180, width / 9));

    for (let i = 0; i < nodes.length; i += 1) {
        const p = nodes[i];
        p.x += p.vx;
        p.y += p.vy;

        // Add subtle wobble for an organic network feel.
        p.x += Math.sin(time + p.phase) * 0.07;
        p.y += Math.cos(time * 0.8 + p.phase) * 0.07;

        if (p.x < -10 || p.x > width + 10) p.vx *= -1;
        if (p.y < -10 || p.y > height + 10) p.vy *= -1;
    }

    for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i];

        for (let j = i + 1; j < nodes.length; j += 1) {
            const b = nodes[j];
            const dx = a.x - b.x;
            const dy = a.y - b.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist > linkDistance) continue;

            const alpha = 1 - dist / linkDistance;
            ctx.strokeStyle = `rgba(52, 211, 153, ${0.24 * alpha})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
        }

        if (pointer.active) {
            const dx = a.x - pointer.x;
            const dy = a.y - pointer.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 190) {
                const alpha = 1 - dist / 190;
                ctx.strokeStyle = `rgba(250, 204, 21, ${0.24 * alpha})`;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(pointer.x, pointer.y);
                ctx.stroke();
            }
        }
    }

    for (let i = 0; i < nodes.length; i += 1) {
        const p = nodes[i];
        const dx = p.x - pointer.x;
        const dy = p.y - pointer.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const glow = pointer.active ? Math.max(0, 1 - dist / 170) : 0;

        ctx.fillStyle =
            glow > 0
                ? `rgba(125, 211, 252, ${0.45 + glow * 0.45})`
                : "rgba(148, 163, 184, 0.55)";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.5 + glow * 1.3, 0, Math.PI * 2);
        ctx.fill();
    }
}

function animate(timeMs: number) {
    if (!ctx) return;

    if (prefersReducedMotion) {
        ctx.clearRect(0, 0, width, height);
        drawWaveGrid(0);
        updateAndDrawNodes(0);
        return;
    }

    // Throttle slightly to reduce GPU churn on lower-end machines.
    if (timeMs - lastFrameTime < 28) {
        rafId = window.requestAnimationFrame(animate);
        return;
    }
    lastFrameTime = timeMs;

    ctx.clearRect(0, 0, width, height);
    drawWaveGrid(timeMs);
    updateAndDrawNodes(timeMs);

    rafId = window.requestAnimationFrame(animate);
}

function onPointerMove(event: PointerEvent) {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.active = true;
}

function onPointerLeave() {
    pointer.active = false;
}

onMounted(() => {
    resizeCanvas();

    window.addEventListener("resize", resizeCanvas);
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerleave", onPointerLeave);

    rafId = window.requestAnimationFrame(animate);
});

onBeforeUnmount(() => {
    window.cancelAnimationFrame(rafId);
    window.removeEventListener("resize", resizeCanvas);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerleave", onPointerLeave);
});
</script>

<template>
    <div class="tech-bg" aria-hidden="true">
        <canvas ref="canvasRef" class="tech-bg-canvas" />
    </div>
</template>

<style scoped>
.tech-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
    opacity: 1;
    mix-blend-mode: screen;
}

.tech-bg-canvas {
    width: 100%;
    height: 100%;
    display: block;
}

@media (max-width: 768px) {
    .tech-bg {
        opacity: 0.78;
    }
}

@media (prefers-reduced-motion: reduce) {
    .tech-bg {
        opacity: 0.4;
    }
}
</style>
