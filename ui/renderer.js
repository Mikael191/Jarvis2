/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║         J.A.R.V.I.S  ─  Singularity UI Engine          ║
 * ║   Maximum visual fidelity · Zero compromise · No chat   ║
 * ╚══════════════════════════════════════════════════════════╝
 *
 * Elements (all CPU-side, no shader compilation needed):
 *  1. 12 Undulating wave rings with per-ring 3D tilt
 *  2. 24 Orbital satellites in randomised 3D orbits
 *  3. 600-particle dynamic core that breathes
 *  4. 8 scanning spoke lines that slowly rotate
 *  5. Periodic "radar ping" echo rings
 *  6. Smooth state transitions (color, speed, glow, heartbeat)
 */

'use strict';

// ─────────────────────────────────────────────────────────────
//  THREE.JS BOILERPLATE
// ─────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
const clock = new THREE.Clock();

const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 200);
camera.position.set(0, 0, 11);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);


// ─────────────────────────────────────────────────────────────
//  PALETTE  (primary = ring/particle colour, accent = spoke/echo)
// ─────────────────────────────────────────────────────────────
const PALETTE = {
    idle: { primary: new THREE.Color(0x00c8ff), accent: new THREE.Color(0x0033dd) },
    listening: { primary: new THREE.Color(0x00ffaa), accent: new THREE.Color(0x007744) },
    thinking: { primary: new THREE.Color(0xffaa00), accent: new THREE.Color(0xff3300) },
    speaking: { primary: new THREE.Color(0x22eeff), accent: new THREE.Color(0x0055ff) },
};

// Live-lerped colour objects – mutated each frame
const lerpColor = new THREE.Color(0x00c8ff);
const lerpAccent = new THREE.Color(0x0033dd);


// ─────────────────────────────────────────────────────────────
//  LIVE STATE
// ─────────────────────────────────────────────────────────────
let currentState = 'idle';
let speedMult = 1.0, targetSpeed = 1.0;
let intensity = 1.0, targetIntensity = 1.0;


// ─────────────────────────────────────────────────────────────
//  MATERIAL FACTORY
// ─────────────────────────────────────────────────────────────
function lineMat(color, opacity) {
    return new THREE.LineBasicMaterial({
        color, transparent: true, opacity,
        blending: THREE.AdditiveBlending, depthWrite: false,
    });
}


// ─────────────────────────────────────────────────────────────
//  ROOT GROUP  (one scale/rotate controls everything)
// ─────────────────────────────────────────────────────────────
const root = new THREE.Group();
scene.add(root);
root.rotation.x = 0.12;          // Slight 3-D angle so rings look spatial


// ═════════════════════════════════════════════════════════════
//  1.  WAVE RINGS
// ═════════════════════════════════════════════════════════════
const RING_N = 12;
const RING_SEG = 180;

const rings = [];
const ringMaterials = [];

for (let i = 0; i < RING_N; i++) {
    const t = i / RING_N;                       // 0 … 1

    // Innermost rings are brightest
    const opacity = THREE.MathUtils.lerp(0.75, 0.12, t);

    const mat = lineMat(lerpColor.clone(), opacity);
    ringMaterials.push(mat);

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(RING_SEG * 3), 3));

    const loop = new THREE.LineLoop(geo, mat);

    // Per-ring physics metadata
    loop.userData = {
        baseR: 0.30 + i * 0.27,
        freq1: 5.0 + i * 0.9,    // # of "waves"
        freq2: 2.5 + i * 0.6,
        amp1: 0.07 + i * 0.018,
        amp2: 0.04,
        rotZ: (0.09 - i * 0.006) * (i % 2 === 0 ? 1 : -1),
        phase: (i / RING_N) * Math.PI * 2,
        tiltX: Math.sin(i * 0.55) * 0.28,
        tiltY: Math.cos(i * 0.38) * 0.20,
    };

    rings.push(loop);
    root.add(loop);
}


// ═════════════════════════════════════════════════════════════
//  2.  ORBITAL SATELLITES
// ═════════════════════════════════════════════════════════════
const SAT_N = 24;
const satGeo = new THREE.BufferGeometry();
const satPos = new Float32Array(SAT_N * 3);
const satData = [];

for (let i = 0; i < SAT_N; i++) {
    satData.push({
        r: 0.55 + Math.random() * 2.4,
        speed: (0.35 + Math.random() * 0.8) * (Math.random() > 0.5 ? 1 : -1),
        tiltX: (Math.random() - 0.5) * Math.PI,
        tiltY: (Math.random() - 0.5) * Math.PI,
        start: Math.random() * Math.PI * 2,
    });
}

satGeo.setAttribute('position', new THREE.BufferAttribute(satPos, 3));

const satMat = new THREE.PointsMaterial({
    color: 0xffffff, size: 0.06,
    transparent: true, opacity: 0.9,
    blending: THREE.AdditiveBlending, depthWrite: false,
});

const satCloud = new THREE.Points(satGeo, satMat);
root.add(satCloud);


// ═════════════════════════════════════════════════════════════
//  3.  CORE PARTICLE SPHERE
// ═════════════════════════════════════════════════════════════
const CORE_N = 600;
const coreGeo = new THREE.BufferGeometry();
const coreData = new Float32Array(CORE_N * 3);

for (let i = 0; i < CORE_N; i++) {
    const r = 0.06 + Math.random() * 0.28;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(Math.random() * 2 - 1);
    coreData[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    coreData[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    coreData[i * 3 + 2] = r * Math.cos(phi);
}
coreGeo.setAttribute('position', new THREE.BufferAttribute(coreData, 3));

const coreMat = new THREE.PointsMaterial({
    color: 0xffffff, size: 0.025,
    transparent: true, opacity: 0.85,
    blending: THREE.AdditiveBlending, depthWrite: false,
});

const coreCloud = new THREE.Points(coreGeo, coreMat);
root.add(coreCloud);


// ═════════════════════════════════════════════════════════════
//  4.  SCANNING SPOKES
// ═════════════════════════════════════════════════════════════
const SPOKE_N = 8;
const spokeGroup = new THREE.Group();
root.add(spokeGroup);

const spokeMat = lineMat(0xffffff, 0.05);

for (let i = 0; i < SPOKE_N; i++) {
    const a = (i / SPOKE_N) * Math.PI * 2;
    const len = 3.8;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(
        new Float32Array([0, 0, 0, Math.cos(a) * len, Math.sin(a) * len, 0]), 3
    ));
    spokeGroup.add(new THREE.Line(geo, spokeMat.clone()));
}


// ═════════════════════════════════════════════════════════════
//  5.  ECHO / RADAR PING RINGS
// ═════════════════════════════════════════════════════════════
const ECHO_MAX = 4;
const echoes = [];
const echoMats = [];

{
    const pts = new Float32Array(RING_SEG * 3);
    for (let j = 0; j < RING_SEG; j++) {
        const a = (j / RING_SEG) * Math.PI * 2;
        pts[j * 3] = Math.cos(a);
        pts[j * 3 + 1] = Math.sin(a);
        pts[j * 3 + 2] = 0;
    }
    for (let e = 0; e < ECHO_MAX; e++) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pts.slice(), 3));
        const mat = new THREE.LineBasicMaterial({
            color: 0x00c8ff, transparent: true, opacity: 0,
            blending: THREE.AdditiveBlending, depthWrite: false,
        });
        echoMats.push(mat);
        const loop = new THREE.LineLoop(geo, mat);
        loop.userData = { active: false, progress: 0 };
        echoes.push(loop);
        root.add(loop);
    }
}

let lastEchoTime = 0;
let nextEchoIdx = 0;
const ECHO_INTERVAL = 2.2; // seconds between pings

function fireEcho() {
    const e = nextEchoIdx % ECHO_MAX;
    const mat = echoMats[e];
    mat.color.copy(lerpColor);
    mat.opacity = 0.7;
    echoes[e].scale.set(0.01, 0.01, 0.01);
    echoes[e].userData = { active: true, progress: 0 };
    nextEchoIdx++;
}


// ═════════════════════════════════════════════════════════════
//  ANIMATE
// ═════════════════════════════════════════════════════════════
let frameRingAccum = 0; // accumulates rotation per-ring independent of framerate

function animate() {
    requestAnimationFrame(animate);

    const dt = clock.getDelta();
    const time = clock.getElapsedTime();

    // ── Smooth state transitions ─────────────────────────────
    speedMult += (targetSpeed - speedMult) * 0.04;
    intensity += (targetIntensity - intensity) * 0.04;

    lerpColor.lerp(PALETTE[currentState].primary, 0.025);
    lerpAccent.lerp(PALETTE[currentState].accent, 0.025);

    // ── Propagate colour to all materials ────────────────────
    ringMaterials.forEach(m => m.color.copy(lerpColor));
    satMat.color.copy(lerpColor);
    coreMat.color.copy(lerpColor);
    echoMats.forEach(m => { if (m.opacity > 0) m.color.lerp(lerpColor, 0.1); });
    spokeMat.color.copy(lerpAccent);

    // ── Root breathing pulse ─────────────────────────────────
    let pulse;
    if (currentState === 'speaking') {
        // Aggressive heartbeat synced to ~12 Hz to simulate voice rhythm
        pulse = 1.0 + Math.abs(Math.sin(time * 13.0)) * 0.14 * intensity;
    } else {
        // Calm, slow breath
        pulse = 1.0 + Math.sin(time * 2.2 * speedMult) * 0.018;
    }
    root.scale.setScalar(pulse);

    // Slow planetary drift so the whole structure feels alive
    root.rotation.y += 0.018 * dt * speedMult;

    // ── Wave rings ───────────────────────────────────────────
    rings.forEach((ring, idx) => {
        const p = ring.userData;
        const tt = time * speedMult;

        const pos = ring.geometry.attributes.position.array;
        for (let j = 0; j < RING_SEG; j++) {
            const a = (j / RING_SEG) * Math.PI * 2 + p.phase;
            const w1 = Math.sin(a * p.freq1 + tt * (1.2 + idx * 0.12)) * p.amp1;
            const w2 = Math.cos(a * p.freq2 - tt * 0.75) * p.amp2;
            const r = p.baseR + w1 + w2;

            pos[j * 3] = Math.cos(a) * r;
            pos[j * 3 + 1] = Math.sin(a) * r;
            // Z ripple fades toward outer rings for a "flat dish" silhouette
            pos[j * 3 + 2] = Math.sin(a * 4 + tt * 1.8) * 0.14 * (1 - idx / RING_N);
        }
        ring.geometry.attributes.position.needsUpdate = true;

        // Gentle wobble tilt
        ring.rotation.x = p.tiltX + Math.sin(time * 0.22 + idx * 0.6) * 0.06;
        ring.rotation.y = p.tiltY + Math.cos(time * 0.17 + idx * 0.5) * 0.06;
        ring.rotation.z += p.rotZ * speedMult * dt;
    });

    // ── Satellites ───────────────────────────────────────────
    satData.forEach((s, i) => {
        const a = s.start + time * s.speed * speedMult;
        const cx = Math.cos(s.tiltY), sx = Math.sin(s.tiltX);
        satPos[i * 3] = Math.cos(a) * s.r * Math.cos(s.tiltY);
        satPos[i * 3 + 1] = Math.sin(a) * s.r * cx;
        satPos[i * 3 + 2] = Math.sin(a) * s.r * sx;
    });
    satGeo.attributes.position.needsUpdate = true;

    // ── Core Particle Cloud ──────────────────────────────────
    coreCloud.rotation.y += 0.9 * dt * speedMult;
    coreCloud.rotation.z += 0.55 * dt * speedMult;

    // Subtle "breathing" of core opacity tied to state intensity
    coreMat.opacity = 0.6 + Math.sin(time * 3.5 * speedMult) * 0.25 * intensity;

    // ── Spokes ───────────────────────────────────────────────
    spokeGroup.rotation.z += 0.28 * dt * speedMult;
    // Spokes get slightly brighter when speaking
    spokeGroup.children.forEach(s => {
        s.material.opacity = 0.04 + (currentState === 'speaking' ? 0.08 : 0);
    });

    // ── Echo Rings ───────────────────────────────────────────
    const echoInterval = ECHO_INTERVAL / speedMult;
    if (time - lastEchoTime > echoInterval) {
        fireEcho();
        lastEchoTime = time;
    }

    echoes.forEach((echo, e) => {
        if (!echo.userData.active) return;
        echo.userData.progress += dt / (1.8 / speedMult);
        const p = echo.userData.progress;
        if (p >= 1) {
            echo.userData.active = false;
            echoMats[e].opacity = 0;
        } else {
            const sc = p * 4.5;
            echo.scale.setScalar(sc);
            echoMats[e].opacity = (1 - p) * 0.55 * intensity;
        }
    });

    renderer.render(scene, camera);
}

animate();


// ─────────────────────────────────────────────────────────────
//  STATE MACHINE
// ─────────────────────────────────────────────────────────────
const STATE_CFG = {
    idle: { speed: 1.0, intensity: 1.0 },
    listening: { speed: 1.45, intensity: 1.3 },
    thinking: { speed: 2.3, intensity: 1.5 },
    speaking: { speed: 1.7, intensity: 2.0 },
};

function setState(s) {
    if (!STATE_CFG[s]) return;
    currentState = s;
    document.body.className = s;               // triggers CSS glow swap
    targetSpeed = STATE_CFG[s].speed;
    targetIntensity = STATE_CFG[s].intensity;
}


// ─────────────────────────────────────────────────────────────
//  IPC  (Electron bridge  +  console.log fallback for testing)
// ─────────────────────────────────────────────────────────────
if (window.jarvisAPI) {
    window.jarvisAPI.onIPC(d => {
        if (d?.type === 'state') setState(d.status || 'idle');
    });
}

(function patchConsole() {
    const orig = console.log.bind(console);
    console.log = (...a) => {
        orig(...a);
        if (typeof a[0] !== 'string') return;
        try {
            const p = JSON.parse(a[0]);
            if (p?.jarvis_ipc?.type === 'state') setState(p.jarvis_ipc.status || 'idle');
        } catch (_) { }
    };
})();


// ─────────────────────────────────────────────────────────────
//  RESPONSIVENESS
// ─────────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
});


// ─────────────────────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────────────────────
setState('idle');
