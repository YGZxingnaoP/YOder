/**
 * WebGL背景效果
 * 使用Three.js创建动态毛玻璃背景
 */
import * as THREE from 'three';

export class WebGLBackground {
    constructor(canvas) {
        this.canvas = canvas;
        this.isPaused = false;
        this.webglAvailable = false;
        this.renderCount = 0;
        this.fallbackActive = false;
        
        try {
            this.scene = new THREE.Scene();
            this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
            this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, powerPreference: 'low-power' });
            
            // 性能优化：限制帧率到 15fps（渐变动画很慢，不需要高帧率）
            this.targetFPS = 15;
            this.frameInterval = 1000 / this.targetFPS;
            this.lastFrameTime = undefined;
            this.webglAvailable = true;
            
            this.init();
            
            // 延迟检测：3秒后检查WebGL是否真的渲染了
            setTimeout(() => {
                if (this.webglAvailable && this.renderCount < 5) {
                    console.warn('WebGL渲染检测失败(3秒内帧数不足)，切换到CSS动画');
                    this.switchToCSSFallback();
                }
            }, 3000);
        } catch (e) {
            console.warn('WebGL不可用，使用CSS动画后备:', e);
            this.switchToCSSFallback();
        }
    }
    
    switchToCSSFallback() {
        this.fallbackActive = true;
        this.webglAvailable = false;
        // 给body加动画渐变背景，不影响壁纸系统
        document.body.classList.add('webgl-fallback');
        // 隐藏canvas
        this.canvas.style.display = 'none';
        // 停止WebGL渲染
        if (this.renderer) {
            try { this.renderer.dispose(); } catch(e) {}
        }
    }
    
    init() {
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        // 限制像素比，避免高分屏性能开销
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        
        // 创建渐变背景
        const geometry = new THREE.PlaneGeometry(2, 2);
        const material = new THREE.ShaderMaterial({
            uniforms: {
                time: { value: 0 },
                resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) }
            },
            vertexShader: `
                varying vec2 vUv;
                void main() {
                    vUv = uv;
                    gl_Position = vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                uniform float time;
                uniform vec2 resolution;
                varying vec2 vUv;
                
                void main() {
                    vec2 uv = vUv;
                    
                    // 动态渐变
                    float t = time * 0.1;
                    vec3 color1 = vec3(0.35, 0.55, 0.85); // 明亮蓝
                    vec3 color2 = vec3(0.65, 0.35, 0.75); // 亮紫
                    vec3 color3 = vec3(0.25, 0.70, 0.65); // 明亮青
                    
                    // 混合颜色
                    float mix1 = smoothstep(0.0, 1.0, uv.x + sin(t) * 0.2);
                    float mix2 = smoothstep(0.0, 1.0, uv.y + cos(t * 0.7) * 0.2);
                    
                    vec3 color = mix(color1, color2, mix1);
                    color = mix(color, color3, mix2);
                    
                    // 添加噪点
                    float noise = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
                    color += noise * 0.02;
                    
                    gl_FragColor = vec4(color, 1.0);
                }
            `
        });
        
        const mesh = new THREE.Mesh(geometry, material);
        this.scene.add(mesh);
        this.material = material;
        
        // 响应窗口大小变化
        window.addEventListener('resize', () => {
            this.renderer.setSize(window.innerWidth, window.innerHeight);
            this.material.uniforms.resolution.value.set(window.innerWidth, window.innerHeight);
        });
        
        this.animate(0);
    }
    
    animate(timestamp) {
        if (!this.webglAvailable || this.fallbackActive) return;
        requestAnimationFrame((t) => this.animate(t));
        
        // 帧率限制：只在间隔时间到达时才渲染
        if (this.isPaused) return;
        if (this.lastFrameTime === undefined) {
            this.lastFrameTime = timestamp;
        }
        const elapsed = timestamp - this.lastFrameTime;
        if (elapsed < this.frameInterval) return;
        this.lastFrameTime = timestamp - (elapsed % this.frameInterval);
        
        try {
            this.material.uniforms.time.value += 0.01;
            this.renderer.render(this.scene, this.camera);
            this.renderCount++;
        } catch (e) {
            console.warn('WebGL渲染失败，切换CSS后备:', e);
            this.switchToCSSFallback();
        }
    }
    
    /**
     * 暂停渲染（切换壁纸时调用）
     */
    pause() {
        this.isPaused = true;
        this.canvas.style.display = 'none';
    }
    
    /**
     * 恢复渲染
     */
    resume() {
        this.isPaused = false;
        if (!this.webglAvailable || this.fallbackActive) {
            document.body.classList.add('webgl-fallback');
            this.canvas.style.display = 'none';
        } else {
            this.canvas.style.display = 'block';
        }
    }
}
