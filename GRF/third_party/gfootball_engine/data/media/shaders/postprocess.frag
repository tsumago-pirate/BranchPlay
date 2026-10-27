// Copyright 2019 Google LLC & Bastiaan Konings
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#version 150

#pragma optimize(on)

uniform sampler2D map_accumulation; // 0
uniform sampler2D map_depth;        // 2

uniform float contextWidth;
uniform float contextHeight;
uniform float contextX;
uniform float contextY;

uniform vec2 cameraClip;

uniform float fogScale;
uniform float focusDistance;

out vec4 stdout;

void main(void) {
  vec2 texCoord = gl_FragCoord.xy;
  texCoord.x -= contextX;
  texCoord.y -= contextY;
  texCoord.x /= contextWidth;
  texCoord.y /= contextHeight;

  // One texel, unfiltered. No edge blend and no occlusion darkening.
  vec3 fragColor = texture(map_accumulation, texCoord).rgb;

  float depth = texture(map_depth, texCoord).x;
  float fragDepth = cameraClip.y / (depth - cameraClip.x);

  // Long lens only. The followed player, and anyone within about 12m of the
  // focus distance, stays the raw pixel. Farther away, five taps soften it.
  if (focusDistance > 1.0) {
    float coc = clamp((abs(fragDepth - focusDistance) - 12.0) / 20.0, 0.0, 1.0);
    if (coc > 0.2) {
      vec2 px = vec2(1.0 / contextWidth, 1.0 / contextHeight) * (coc * 5.0);
      vec3 soft = fragColor;
      soft += texture(map_accumulation, texCoord + vec2(px.x, 0.0)).rgb;
      soft += texture(map_accumulation, texCoord - vec2(px.x, 0.0)).rgb;
      soft += texture(map_accumulation, texCoord + vec2(0.0, px.y)).rgb;
      soft += texture(map_accumulation, texCoord - vec2(0.0, px.y)).rgb;
      fragColor = mix(fragColor, soft * 0.2, coc);
    }
  }

  vec3 fogColor = vec3(0.85, 0.85, 0.9);
  float fogFactor = clamp(fragDepth * 0.01 * (1.0 - fogScale) - 0.16 * fogScale, 0.0, 0.25);
  fragColor = fragColor * (1.0 - fogFactor) + fogColor * fogFactor;
  // Cleared background is 1. A looser test also caught the far half of the
  // pitch from eye height: a near cap of a few centimeters packs that ground
  // into the last thousandth of the depth buffer, so it was painted as sky.
  if (depth > 0.99999) fragColor = fogColor;

  stdout = vec4(clamp(fragColor, 0.0, 1.0), 0.0);
}
