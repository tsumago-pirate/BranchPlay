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

uniform sampler2D map_albedo; // 0
uniform sampler2D map_aux;    // 3

uniform float contextWidth;
uniform float contextHeight;
uniform float contextX;
uniform float contextY;

out vec4 stdout0;

void main(void) {
  vec2 texCoord = gl_FragCoord.xy;
  texCoord.x -= contextX;
  texCoord.y -= contextY;
  texCoord.x /= contextWidth;
  texCoord.y /= contextHeight;

  // Fill light only. The old pass also grayed the color, tinted it, and ran
  // a 32-tap occlusion loop whose result was then blurred. None of that is
  // drawn anymore: it cost a full-screen gather and muddied the kits.
  vec3 base = texture(map_albedo, texCoord).xyz * 0.15;
  float selfIllumination = texture(map_aux, texCoord).w;
  stdout0 = vec4(clamp(base * (1.0 + selfIllumination), 0.0, 1.0), 1.0);
}
