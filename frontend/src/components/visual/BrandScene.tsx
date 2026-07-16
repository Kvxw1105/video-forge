import { useEffect, useRef } from 'react'
import * as THREE from 'three'

const PARTICLE_COUNT = 720

function createPaperPlane(side: -1 | 1) {
  const width = 8.5
  const height = 12
  const inner = side * 0.48
  const outer = side * width
  const vertices = new Float32Array([
    outer, height, 0,
    inner, height, 0,
    side * 0.22, 3.8, 0,
    outer, height, 0,
    side * 0.22, 3.8, 0,
    side * 0.66, -0.4, 0,
    outer, height, 0,
    side * 0.66, -0.4, 0,
    side * 0.28, -5.8, 0,
    outer, height, 0,
    side * 0.28, -5.8, 0,
    outer, -height, 0,
  ])
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3))
  geometry.computeVertexNormals()

  const material = new THREE.MeshBasicMaterial({
    color: side === -1 ? 0x17130f : 0x211a14,
    transparent: true,
    opacity: 0.72,
    side: THREE.DoubleSide,
  })

  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.z = -1.8
  mesh.rotation.z = side * 0.025
  return mesh
}

function createRiftLine() {
  const points = [
    new THREE.Vector3(-0.16, 7, 0),
    new THREE.Vector3(0.18, 4.5, 0.08),
    new THREE.Vector3(-0.08, 2.4, 0.02),
    new THREE.Vector3(0.24, 0.2, 0.12),
    new THREE.Vector3(-0.1, -2.1, 0.02),
    new THREE.Vector3(0.12, -4.4, 0.08),
    new THREE.Vector3(-0.2, -7, 0),
  ]
  const curve = new THREE.CatmullRomCurve3(points)
  const geometry = new THREE.TubeGeometry(curve, 80, 0.018, 6, false)
  const material = new THREE.MeshBasicMaterial({
    color: 0xe1bd7d,
    transparent: true,
    opacity: 0.58,
  })
  return new THREE.Mesh(geometry, material)
}

export default function BrandScene() {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x090807, 0.055)

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100)
    camera.position.set(0, 0, 15)

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    mount.appendChild(renderer.domElement)

    const world = new THREE.Group()
    world.add(createPaperPlane(-1), createPaperPlane(1))

    const rift = createRiftLine()
    world.add(rift)

    const haloGeometry = new THREE.PlaneGeometry(1.5, 15)
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0x9b653d,
      transparent: true,
      opacity: 0.055,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const halo = new THREE.Mesh(haloGeometry, haloMaterial)
    halo.position.z = -0.3
    halo.rotation.z = -0.025
    world.add(halo)

    const particlePositions = new Float32Array(PARTICLE_COUNT * 3)
    for (let index = 0; index < PARTICLE_COUNT; index += 1) {
      const offset = index * 3
      const nearRift = Math.random() > 0.58
      particlePositions[offset] = nearRift
        ? (Math.random() - 0.5) * 2.2
        : (Math.random() - 0.5) * 20
      particlePositions[offset + 1] = (Math.random() - 0.5) * 14
      particlePositions[offset + 2] = (Math.random() - 0.5) * 8 - 1
    }

    const particleGeometry = new THREE.BufferGeometry()
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3))
    const particleMaterial = new THREE.PointsMaterial({
      color: 0xd0aa72,
      size: 0.028,
      transparent: true,
      opacity: 0.4,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const particles = new THREE.Points(particleGeometry, particleMaterial)
    world.add(particles)
    scene.add(world)

    const pointer = new THREE.Vector2()
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let frameId = 0

    const resize = () => {
      const { clientWidth, clientHeight } = mount
      renderer.setSize(clientWidth, clientHeight, false)
      camera.aspect = clientWidth / Math.max(clientHeight, 1)
      camera.updateProjectionMatrix()
      world.scale.setScalar(clientWidth < 900 ? 0.82 : 1)
    }

    const onPointerMove = (event: PointerEvent) => {
      pointer.x = (event.clientX / window.innerWidth - 0.5) * 2
      pointer.y = (event.clientY / window.innerHeight - 0.5) * 2
    }

    const clock = new THREE.Clock()
    const render = () => {
      const elapsed = clock.getElapsedTime()
      const motion = reducedMotion ? 0 : 1
      world.rotation.y += (pointer.x * 0.018 * motion - world.rotation.y) * 0.018
      world.rotation.x += (-pointer.y * 0.01 * motion - world.rotation.x) * 0.018
      particles.rotation.z = elapsed * 0.004 * motion
      particles.position.y = Math.sin(elapsed * 0.18) * 0.08 * motion
      ;(rift.material as THREE.MeshBasicMaterial).opacity = 0.5 + Math.sin(elapsed * 0.7) * 0.08 * motion
      renderer.render(scene, camera)
      frameId = window.requestAnimationFrame(render)
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(mount)
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    resize()
    render()

    return () => {
      window.cancelAnimationFrame(frameId)
      resizeObserver.disconnect()
      window.removeEventListener('pointermove', onPointerMove)
      particleGeometry.dispose()
      particleMaterial.dispose()
      haloGeometry.dispose()
      haloMaterial.dispose()
      world.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return
        object.geometry.dispose()
        if (Array.isArray(object.material)) object.material.forEach(material => material.dispose())
        else object.material.dispose()
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  return <div ref={mountRef} className="brand-scene" aria-hidden="true" />
}
