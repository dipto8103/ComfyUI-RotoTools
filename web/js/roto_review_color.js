// ComfyUI-RotoTools: Roto Review player. Based on ComfyUI-KM-VideoReview (web/js/videoReviewColor.js)
// by Kasun Malinda, https://github.com/KasunMalinda/ComfyUI-KM-VideoReview
// MIT License, Copyright (c) 2026 Kasun Malinda (full text in LICENSE-KM-VideoReview).
// RotoTools change: transform() also accepts a canvas (the roto composited over a background / its matte).
//
// VRColorEngine — GPU exposure/gamma stage for VideoReviewPlayer.
// Applies exposure (stops) and display gamma directly to the preview pixels,
// entirely on the GPU so riding the sliders never re-runs the workflow.
// Side-effect-free module: only exports the class.

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const FRAG = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_exposure; // stops
uniform float u_gamma;    // display gamma adjust
void main() {
  vec3 c = texture2D(u_tex, v_uv).rgb * exp2(u_exposure);
  c = clamp(c, 0.0, 1.0);
  // Epsilon guards: some older GPU drivers return NaN from pow() at base 0 even
  // though the spec defines it for positive exponents. 1e-10 is far below 8-bit
  // quantization, so blacks stay black at any gamma in the slider range.
  if (u_gamma != 1.0) c = pow(max(c, 1e-10), vec3(1.0 / max(u_gamma, 1e-4)));
  gl_FragColor = vec4(c, 1.0);
}`;

const MAX_TEXTURES = 16;

export class VRColorEngine {
  constructor() {
    this.ok = false;
    try {
      this.canvas = document.createElement("canvas");
      const gl = (this.gl = this.canvas.getContext("webgl", {
        premultipliedAlpha: false,
        preserveDrawingBuffer: true,
        antialias: false,
        depth: false,
      }));
      if (!gl) return;
      const compile = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
          throw new Error(gl.getShaderInfoLog(s));
        }
        return s;
      };
      const prog = (this.prog = gl.createProgram());
      gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(prog));
      }
      gl.useProgram(prog);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, "a_pos");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      this.u = {
        exposure: gl.getUniformLocation(prog, "u_exposure"),
        gamma: gl.getUniformLocation(prog, "u_gamma"),
      };
      this.texCache = new Map(); // Image -> WebGLTexture (Map preserves insertion order for LRU)
      this.ok = true;
    } catch (e) {
      console.warn("[videoreview] WebGL engine unavailable:", e);
      this.ok = false;
    }
  }

  #texture(img) {
    const gl = this.gl;
    let tex = this.texCache.get(img);
    if (tex) {
      // refresh LRU position
      this.texCache.delete(img);
      this.texCache.set(img, tex);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      return tex;
    }
    tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.texCache.set(img, tex);
    if (this.texCache.size > MAX_TEXTURES) {
      const [oldImg, oldTex] = this.texCache.entries().next().value;
      gl.deleteTexture(oldTex);
      this.texCache.delete(oldImg);
    }
    return tex;
  }

  // Transform `img` (an HTMLImageElement) and return a canvas of the same size
  // holding the result. Returns null if the engine is unusable.
  transform(img, params) {
    const iw = img?.naturalWidth || img?.width; // Image or (RotoTools) canvas
    if (!this.ok || !iw) return null;
    const gl = this.gl;
    const w = iw, h = img.naturalHeight || img.height;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    this.#texture(img);
    gl.uniform1f(this.u.exposure, params.exposure);
    gl.uniform1f(this.u.gamma, params.gamma);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    return this.canvas;
  }

  // Free all cached textures (call when a new run replaces the frame set, so
  // stale textures don't sit in VRAM waiting for LRU eviction).
  clearCache() {
    if (!this.ok) return;
    for (const tex of this.texCache.values()) this.gl.deleteTexture(tex);
    this.texCache.clear();
  }

  dispose() {
    if (!this.ok) return;
    this.clearCache();
    this.gl.getExtension("WEBGL_lose_context")?.loseContext();
    this.ok = false;
  }
}
