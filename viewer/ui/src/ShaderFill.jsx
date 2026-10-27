import { useEffect, useRef } from 'react'
import * as THREE from 'three'

const vertexShader = `
in vec3 position;
in vec2 uv;
out vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`

const fragmentShader = `
precision highp float;
uniform float uTime;
uniform float uSeed;
in vec2 vUv;
out vec4 fragColor;

void main() {
  float t = uTime * 0.35 + uSeed * 6.2831853;
  vec2 uv = vUv + vec2(uSeed * 3.1, uSeed * 2.7);
  float a = sin(uv.x * 2.1 + uv.y * 1.35 + t);
  float b = sin(uv.x * -1.45 + uv.y * 2.5 - t * 0.72);
  float c = sin((uv.x + uv.y) * 2.8 + t * 0.45);
  float ang = uSeed * 6.2831853;
  float grade = dot(vUv - 0.5, vec2(cos(ang), sin(ang)));
  float lift = clamp(0.48 + a * 0.22 + b * 0.16 + c * 0.12 + grade * 0.46, 0.0, 1.0);
  vec3 lo = vec3(0.035, 0.038, 0.036);
  vec3 hi = vec3(0.158, 0.166, 0.160);
  fragColor = vec4(mix(lo, hi, lift), 1.0);
}
`

let seedCursor = Math.random()

function nextSeed() {
  seedCursor = (seedCursor + 0.6180339887) % 1
  return seedCursor
}

export default function ShaderFill() {
  const canvasRef = useRef(null)
  const seedRef = useRef(nextSeed())

  useEffect(() => {
    const canvas = canvasRef.current
    const parent = canvas.parentElement
    if (!parent) return undefined

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      alpha: false,
      powerPreference: 'low-power',
    })
    renderer.setClearColor(0x090a09, 1)
    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
    const material = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uSeed: { value: seedRef.current },
      },
    })
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material)
    scene.add(mesh)

    const fit = () => {
      const width = Math.max(1, parent.clientWidth)
      const height = Math.max(1, parent.clientHeight)
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
      renderer.setSize(width, height, false)
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(parent)

    let frame = 0
    const started = performance.now()
    const draw = (now) => {
      material.uniforms.uTime.value = (now - started) / 1000
      renderer.render(scene, camera)
      frame = window.requestAnimationFrame(draw)
    }
    frame = window.requestAnimationFrame(draw)

    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      mesh.geometry.dispose()
      material.dispose()
      renderer.dispose()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 h-full w-full"
    />
  )
}
