# SIG placement review for 26.10.0

97 of 254 entries in the report were placed under a SIG by a guess rather than by a `sig/*` label on the pull request. Measured against labelled pull requests, roughly three guesses in four agree with the label, so some of these are under the wrong heading.

To correct one, either:

- add the right `sig/*` label to the pull request on GitHub (preferred: the next run picks it up and the fix outlives this report), or
- set `manual_override_sig` on that pull request in the release data JSON, which survives re-runs.

Nothing in this file is published. It is regenerated on every run.

## Needs a decision (0)

_None._

## Check these first (23)

The evidence is thin: a tie, a title keyword with no file to back it, a winner that owns under 60% of the files that matched anything, or a title that points to a different SIG than the files do.

| PR | Title | Placed under | Evidence |
|---|---|---|---|
| [o3de#19948](https://github.com/o3de/o3de/pull/19948) | fix(security): Update vulnerable GitPython and urllib3 dependencies | SIG-Build | file map: 1 of 1 files; the title suggests security |
| [o3de#19970](https://github.com/o3de/o3de/pull/19970) | Fixes Mac bundling issues with Qt6 | SIG-Build | file map: 1 of 1 files; the title suggests platform |
| [o3de#19571](https://github.com/o3de/o3de/pull/19571) | Mac ARM64 integration | SIG-Content | file map: 93 of 100 files (also core 7); file list truncated at 100; the title suggests platform |
| [o3de#19593](https://github.com/o3de/o3de/pull/19593) | Fix Wignored-attributes warnings | SIG-Content | file map: 1 of 2 files (also core 1); tie, settled alphabetically |
| [o3de#19734](https://github.com/o3de/o3de/pull/19734) | libtiff: migrate legacy typedefs to C99 standard types | SIG-Content | file map: 1 of 2 files (also graphics-audio 1); tie, settled alphabetically |
| [o3de#19934](https://github.com/o3de/o3de/pull/19934) | Reflect SmoothCriticallyDamped function for scripting and add SmoothStep | SIG-Content | file map: 16 of 27 files (also simulation 11); the title suggests core |
| [o3de#20126](https://github.com/o3de/o3de/pull/20126) | AzToolsFramework: initialize savedJobStatus in unfiltered product queries | SIG-Content | file map: 1 of 1 files; the title suggests core |
| [o3de#19801](https://github.com/o3de/o3de/pull/19801) | Fix Linux gamepad support when only the libevdev runtime is installed | SIG-Core | file map: 1 of 1 files; the title suggests platform |
| [o3de#19856](https://github.com/o3de/o3de/pull/19856) | Fixes network-related crashes during Init of entities and dangling child entities | SIG-Core | file map: 4 of 7 files (also content 2, network 1); the title suggests network |
| [o3de#19870](https://github.com/o3de/o3de/pull/19870) | Mac fix lrelease rpath | SIG-Core | file map: 1 of 1 files; the title suggests platform |
| [o3de#19882](https://github.com/o3de/o3de/pull/19882) | Fixes imgui console input bug | SIG-Core | file map: 2 of 2 files; the title suggests graphics-audio |
| [o3de#19952](https://github.com/o3de/o3de/pull/19952) | fix(content): Correct spelling of Groundplane asset folder path | SIG-Core | file map: 4 of 30 files (also graphics-audio 4, simulation 2); tie, settled alphabetically |
| [o3de-extras#1087](https://github.com/o3de/o3de-extras/pull/1087) | Fix incorrect AZ::IO::Path constructor | SIG-Core | title keyword only ("az::"); no changed file is owned by a SIG |
| [o3de#19630](https://github.com/o3de/o3de/pull/19630) | Add imgui.ini to .gitignore | SIG-Graphics-Audio | title keyword only ("imgui"); no changed file is owned by a SIG |
| [o3de#19964](https://github.com/o3de/o3de/pull/19964) | Fix LyShine editor crash from zero-size viewport window | SIG-Graphics-Audio | file map: 1 of 1 files; the title suggests content |
| [o3de#19992](https://github.com/o3de/o3de/pull/19992) | Convert D3D12MemoryAllocator 3p to FetchContent. | SIG-Graphics-Audio | file map: 11 of 11 files; the title suggests build |
| [o3de-extras#1090](https://github.com/o3de/o3de-extras/pull/1090) | Upgrade Tracy profiler to 1.14.1, also mark the tracy frame end to RHI OnFrameEnd. | SIG-Graphics-Audio | title keyword only ("rhi"); no changed file is owned by a SIG |
| [o3de#19591](https://github.com/o3de/o3de/pull/19591) | MotionMatching's debugdraw, disable by default. | SIG-Simulation | file map: 1 of 1 files; the title suggests content |
| [o3de#19613](https://github.com/o3de/o3de/pull/19613) | Fixed MotionMatching ScriptCanvas demo files | SIG-Simulation | file map: 3 of 3 files; the title suggests content |
| [o3de#19732](https://github.com/o3de/o3de/pull/19732) | Switch to parallel_for in MotionMatching gem init | SIG-Simulation | file map: 1 of 1 files; the title suggests content |
| [o3de-extras#1075](https://github.com/o3de/o3de-extras/pull/1075) | RobotImporter Gem - passing referenced assets and import status through EBuses. | SIG-Simulation | title keyword only ("robot"); no changed file is owned by a SIG |
| [o3de-extras#1076](https://github.com/o3de/o3de-extras/pull/1076) | Fix deprecated gmock Invoke() usage in SimulationInterfaces tests | SIG-Simulation | file map: 1 of 1 files; the title suggests testing |
| [o3de-extras#1085](https://github.com/o3de/o3de-extras/pull/1085) | Refactor of RobotImporter asset detection and copying - deduplication across diffrent import method. | SIG-Simulation | title keyword only ("robot"); no changed file is owned by a SIG |

## Placed by file ownership (74)

One SIG clearly owns most of the changed files. Usually right; wrong when the change belongs to a different SIG than the code it touches, such as a build fix inside editor code.

| PR | Title | Placed under | Evidence |
|---|---|---|---|
| [o3de#19606](https://github.com/o3de/o3de/pull/19606) | Removal of chardet and set charset-normalizer in place of it | SIG-Build | file map: 3 of 4 files |
| [o3de#19607](https://github.com/o3de/o3de/pull/19607) | Add support for non-AppleClang compilers on macOS | SIG-Build | file map: 2 of 3 files (also graphics-audio 1) |
| [o3de#19812](https://github.com/o3de/o3de/pull/19812) | fix(cmake): no-fast-math prefixed with PRIVATE | SIG-Build | file map: 1 of 1 files |
| [o3de#19847](https://github.com/o3de/o3de/pull/19847) | Update 3P version and SHA256 hash for pyside6-6.10.2 | SIG-Build | file map: 3 of 3 files |
| [o3de#19849](https://github.com/o3de/o3de/pull/19849) | Fixes the autogen cmake script to not trigger a full cmake regenerate… | SIG-Build | file map: 1 of 1 files |
| [o3de#19903](https://github.com/o3de/o3de/pull/19903) | Trust the user when they specify an engine | SIG-Build | file map: 1 of 1 files |
| [o3de#19914](https://github.com/o3de/o3de/pull/19914) | Update 3P version and SHA256 hash for expat-2.7.3 | SIG-Build | file map: 1 of 1 files |
| [o3de#19915](https://github.com/o3de/o3de/pull/19915) | LYPython: keep editable pip install for out-of-source packages on installed engines | SIG-Build | file map: 1 of 1 files |
| [o3de#19941](https://github.com/o3de/o3de/pull/19941) | Fix build: fetch content misses extension | SIG-Build | file map: 1 of 1 files |
| [o3de#19950](https://github.com/o3de/o3de/pull/19950) | fix(build): Preserve argument quoting and tilde expansion in o3de.sh | SIG-Build | file map: 1 of 1 files |
| [o3de#19953](https://github.com/o3de/o3de/pull/19953) | Remove nightly schedule from AR Canary workflow | SIG-Build | file map: 1 of 1 files |
| [o3de#19967](https://github.com/o3de/o3de/pull/19967) | Update 3P version and SHA256 hash for DirectXShaderCompilerDxc-1.8.2505.1 | SIG-Build | file map: 1 of 1 files |
| [o3de#19997](https://github.com/o3de/o3de/pull/19997) | Update 3P version and SHA256 hash for freetype-2.11.1 | SIG-Build | file map: 1 of 1 files |
| [o3de#20135](https://github.com/o3de/o3de/pull/20135) | Update lfs, package, and AR package urls | SIG-Build | file map: 6 of 7 files |
| [o3de#19429](https://github.com/o3de/o3de/pull/19429) | Fix incorrect flag check in Assimp scene importing | SIG-Content | file map: 1 of 1 files |
| [o3de#19590](https://github.com/o3de/o3de/pull/19590) | \[LUA Editor\] Prevent wrong settings being applied when canceling | SIG-Content | file map: 3 of 3 files |
| [o3de#19605](https://github.com/o3de/o3de/pull/19605) | \[Editor\] Fix pick (translate, rotate, scale) objects which are far way from origin | SIG-Content | file map: 1 of 1 files |
| [o3de#19625](https://github.com/o3de/o3de/pull/19625) | Add patch file for assimp to fix tinyusd missing includes | SIG-Content | file map: 2 of 2 files |
| [o3de#19678](https://github.com/o3de/o3de/pull/19678) | Generic Asset Group now affects \[New\] menu, grouping assets. | SIG-Content | file map: 3 of 3 files |
| [o3de#19685](https://github.com/o3de/o3de/pull/19685) | Selecting file entities outside of outliner deselects the outliner | SIG-Content | file map: 2 of 2 files |
| [o3de#19710](https://github.com/o3de/o3de/pull/19710) | Upgrade Assimp to 6.0.4 | SIG-Content | file map: 2 of 2 files |
| [o3de#19735](https://github.com/o3de/o3de/pull/19735) | Gem-based Level Loading and Saving | SIG-Content | file map: 16 of 16 files |
| [o3de#19797](https://github.com/o3de/o3de/pull/19797) | Fix editor crash creating an entity with no level loaded | SIG-Content | file map: 2 of 2 files |
| [o3de#19816](https://github.com/o3de/o3de/pull/19816) | Fixed editor \`TransformComponent\` not notifying of child add/removal | SIG-Content | file map: 1 of 1 files |
| [o3de#19871](https://github.com/o3de/o3de/pull/19871) | Fix build: missing header | SIG-Content | file map: 3 of 5 files (also graphics-audio 1, simulation 1) |
| [o3de#19912](https://github.com/o3de/o3de/pull/19912) | Do not populate recent files menu too early | SIG-Content | file map: 1 of 1 files |
| [o3de#19933](https://github.com/o3de/o3de/pull/19933) | Fix non-unity build | SIG-Content | file map: 5 of 6 files (also core 1) |
| [o3de#19984](https://github.com/o3de/o3de/pull/19984) | Replace legacy #ifndef include guards with #pragma once | SIG-Content | file map: 100 of 100 files; file list truncated at 100 |
| [o3de#20112](https://github.com/o3de/o3de/pull/20112) | Fix non-unity build | SIG-Content | file map: 1 of 1 files |
| [o3de#19614](https://github.com/o3de/o3de/pull/19614) | Refactor AZStd Allocators | SIG-Core | file map: 17 of 21 files (also content 2) |
| [o3de#19733](https://github.com/o3de/o3de/pull/19733) | AzCore/Script: drop redundant \<Lua/lobject.h> include | SIG-Core | file map: 1 of 1 files |
| [o3de#19852](https://github.com/o3de/o3de/pull/19852) | Fix lrelease rpath | SIG-Core | file map: 1 of 1 files |
| [o3de#19853](https://github.com/o3de/o3de/pull/19853) | Adds the ability to provide a functor callback to autocomplete AZ console command arguments | SIG-Core | file map: 4 of 4 files |
| [o3de#19905](https://github.com/o3de/o3de/pull/19905) | Remove \`engines_path\` from registration flow. | SIG-Core | file map: 1 of 1 files |
| [o3de#19963](https://github.com/o3de/o3de/pull/19963) | Fix LuaIDE IPC, file path case preservation and wrong document invalidation | SIG-Core | file map: 4 of 5 files (also content 1) |
| [o3de#19985](https://github.com/o3de/o3de/pull/19985) | Remove dlmalloc and nedmalloc from AzCore. | SIG-Core | file map: 3 of 3 files |
| [o3de#20113](https://github.com/o3de/o3de/pull/20113) | Fix oversized SystemFile transfers on Unix-like platforms | SIG-Core | file map: 2 of 2 files |
| [o3de-extras#1064](https://github.com/o3de/o3de-extras/pull/1064) | Remove unused automoc and autorcc in project template | SIG-Core | file map: 1 of 1 files |
| [o3de#19654](https://github.com/o3de/o3de/pull/19654) | Stars: Make exposure, radius, and twinkle rate accessible via ebus and expose the methods to behavior context for scripting | SIG-Graphics-Audio | file map: 9 of 10 files (also content 1) |
| [o3de#19656](https://github.com/o3de/o3de/pull/19656) | Split opaque Unlit into a dedicated shader path | SIG-Graphics-Audio | file map: 4 of 4 files |
| [o3de#19659](https://github.com/o3de/o3de/pull/19659) | Stars: Account for when negative exposure, radius factor, or twinkle rate is passed to ebus setters | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#19709](https://github.com/o3de/o3de/pull/19709) | Fix for choppy mouse movement in FlyCameraInputComponent and replace Cry_Math types | SIG-Graphics-Audio | file map: 2 of 2 files |
| [o3de#19737](https://github.com/o3de/o3de/pull/19737) | Microphone: gate libsamplerate dependency on PAL_TRAIT_MICROPHONE_USES_LIBSAMPLERATE | SIG-Graphics-Audio | file map: 6 of 6 files |
| [o3de#19756](https://github.com/o3de/o3de/pull/19756) | OpenParticleSystem/ParticleBuilder: declare material JobDependency by path on cold cache | SIG-Graphics-Audio | file map: 2 of 2 files |
| [o3de#19825](https://github.com/o3de/o3de/pull/19825) | Define TIFF_DISABLE_DEPRECATED ahead of every tiffio.h include | SIG-Graphics-Audio | file map: 2 of 3 files (also content 1) |
| [o3de#19865](https://github.com/o3de/o3de/pull/19865) | Preloads the material asset | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#19891](https://github.com/o3de/o3de/pull/19891) | Upgrade meshoptimizer to v1.2 | SIG-Graphics-Audio | file map: 3 of 5 files (also content 2) |
| [o3de#19927](https://github.com/o3de/o3de/pull/19927) | Modify the way import os, and remove useless return | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#19976](https://github.com/o3de/o3de/pull/19976) | AudioSystem Gem Editor and Engine fixes: FileCacheManager dangling pointer and invisible Connection Properties. | SIG-Graphics-Audio | CODEOWNERS: 2 of 2 files |
| [o3de#19994](https://github.com/o3de/o3de/pull/19994) | Fix Cutout SSAO Artifacts and Blended Shadows in the Unlit Shader | SIG-Graphics-Audio | file map: 5 of 5 files |
| [o3de#20034](https://github.com/o3de/o3de/pull/20034) | Fix Metal color clears for render scopes without draw work | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#20090](https://github.com/o3de/o3de/pull/20090) | Decal issue fixes (ported from @wdstudiosma, supercedes #20050) | SIG-Graphics-Audio | file map: 49 of 54 files (also content 3) |
| [o3de#20127](https://github.com/o3de/o3de/pull/20127) | Atom: stage azslc inside the AssetProcessor bundle on macOS | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#20158](https://github.com/o3de/o3de/pull/20158) | Include MiniAudio in unified launcher builds | SIG-Graphics-Audio | file map: 1 of 1 files |
| [o3de#19879](https://github.com/o3de/o3de/pull/19879) | Fix AutoComponent jinja narrowing conversions for vector properties | SIG-Network | file map: 1 of 1 files |
| [o3de#19944](https://github.com/o3de/o3de/pull/19944) | Fix server crash by disconnecting NetworkRigidBody handlers on deactivate | SIG-Network | file map: 1 of 1 files |
| [o3de#20146](https://github.com/o3de/o3de/pull/20146) | Fix crash when a DTLS handshake fails (DtlsEndpoint::PerformHandshakeInternal) | SIG-Network | file map: 1 of 1 files |
| [o3de-extras#1055](https://github.com/o3de/o3de-extras/pull/1055) | Update multiplayer template to fix compile issue with floats. | SIG-Network | CODEOWNERS: 2 of 3 files |
| [o3de-extras#1057](https://github.com/o3de/o3de-extras/pull/1057) | Update multiplayer template to fix compile issue with floats. | SIG-Network | CODEOWNERS: 2 of 3 files |
| [o3de#19707](https://github.com/o3de/o3de/pull/19707) | Add DetourCrowd from recastnavigation | SIG-Simulation | file map: 14 of 14 files |
| [o3de#19726](https://github.com/o3de/o3de/pull/19726) | PhysX4 Deprecation | SIG-Simulation | file map: 23 of 31 files (also core 4, content 3, build 1) |
| [o3de#19742](https://github.com/o3de/o3de/pull/19742) | Continuation of PhysX4 removal | SIG-Simulation | file map: 10 of 12 files (also build 1, core 1) |
| [o3de#19769](https://github.com/o3de/o3de/pull/19769) | Added additional \`PropertyVisibility\` for \`Tag\` and \`ContactEffset\` to AzPhysics \`ColliderConfiguration\` | SIG-Simulation | file map: 2 of 2 files |
| [o3de#19826](https://github.com/o3de/o3de/pull/19826) | Expose PhysX enhanced-determinism flag via SceneConfiguration. | SIG-Simulation | file map: 3 of 3 files |
| [o3de#20053](https://github.com/o3de/o3de/pull/20053) | Support automatic inertia calculation in ArticulationLink | SIG-Simulation | file map: 4 of 4 files |
| [o3de-extras#1034](https://github.com/o3de/o3de-extras/pull/1034) | Fixes to manipulation components and ROS 2 gems | SIG-Simulation | CODEOWNERS: 2 of 7 files |
| [o3de-extras#1037](https://github.com/o3de/o3de-extras/pull/1037) | ROS2: Rosify namespace if needed | SIG-Simulation | CODEOWNERS: 1 of 1 files |
| [o3de-extras#1039](https://github.com/o3de/o3de-extras/pull/1039) | \[Simulation Interfaces\] Add support for simulation_interfaces/srv/SpawnEntities.srv | SIG-Simulation | file map: 6 of 6 files |
| [o3de-extras#1044](https://github.com/o3de/o3de-extras/pull/1044) | Support simulation_interfaces 2.1.0 package alongside 1.4.0/1.5.0/1.6.0 | SIG-Simulation | CODEOWNERS: 3 of 9 files |
| [o3de-extras#1045](https://github.com/o3de/o3de-extras/pull/1045) | Fix development (and tests) | SIG-Simulation | CODEOWNERS: 1 of 4 files |
| [o3de-extras#1056](https://github.com/o3de/o3de-extras/pull/1056) | \[SimulationIntefaces\] Fix compilation issue with older ROS 2 simulation-interfaces packages | SIG-Simulation | file map: 1 of 1 files |
| [o3de-extras#1065](https://github.com/o3de/o3de-extras/pull/1065) | Added GetFrameTransform to the ROS2Frame EBus | SIG-Simulation | CODEOWNERS: 4 of 4 files |
| [o3de-extras#1069](https://github.com/o3de/o3de-extras/pull/1069) | Fix build after o3de#19951 | SIG-Simulation | file map: 1 of 2 files |
| [o3de-extras#1078](https://github.com/o3de/o3de-extras/pull/1078) | Fix ResetSimulationService handler: bits not ints | SIG-Simulation | file map: 2 of 2 files |

## More than one SIG label (22)

These carry several `sig/*` labels and appear once, under the first in alphabetical order. Remove the labels that do not apply, or override.

| PR | Title | Placed under | Evidence |
|---|---|---|---|
| [o3de#19109](https://github.com/o3de/o3de/pull/19109) | Add configuration files for Emscripten platform | SIG-Build | labels: build, core |
| [o3de#19477](https://github.com/o3de/o3de/pull/19477) | Initial Wayland support. | SIG-Build | labels: build, core, graphics-audio, platform |
| [o3de#19552](https://github.com/o3de/o3de/pull/19552) | Automated Review Workflows for iOS and Mac | SIG-Build | labels: build, core |
| [o3de#19620](https://github.com/o3de/o3de/pull/19620) | Alternative fix for the failing test - run serially rather than parallel | SIG-Build | labels: build, testing |
| [o3de#19622](https://github.com/o3de/o3de/pull/19622) | O3DE Fetch Content | SIG-Build | labels: build, content |
| [o3de#19626](https://github.com/o3de/o3de/pull/19626) | Fixes a compile error with assimp | SIG-Build | labels: build, content |
| [o3de#19716](https://github.com/o3de/o3de/pull/19716) | Add Canary AR and update AR to Clang 18 | SIG-Build | labels: build, core, platform |
| [o3de#19924](https://github.com/o3de/o3de/pull/19924) | Fix C++26 Compilation | SIG-Build | labels: build, core |
| [o3de#20070](https://github.com/o3de/o3de/pull/20070) | Fixes broken monolithic compile for meshoptimizer | SIG-Build | labels: build, graphics-audio |
| [o3de-extras#1089](https://github.com/o3de/o3de-extras/pull/1089) | Add workflow to test simulation Gems for PR | SIG-Build | labels: build, simulation |
| [o3de#19681](https://github.com/o3de/o3de/pull/19681) | Windows successfully alt tab independently. | SIG-Content | labels: content, graphics-audio, platform |
| [o3de#19713](https://github.com/o3de/o3de/pull/19713) | Colour gradient primitive and QtField | SIG-Content | labels: content, core, simulation |
| [o3de#19741](https://github.com/o3de/o3de/pull/19741) | Fix a buffer overflow when loading 3D (Volumetric) texture in the editor | SIG-Content | labels: content, graphics-audio |
| [o3de#19767](https://github.com/o3de/o3de/pull/19767) | Fix typo: 'a empty xx' should be 'an empty xx' | SIG-Content | labels: content, core |
| [o3de#19827](https://github.com/o3de/o3de/pull/19827) | Entity Activation Testing and MP fixes | SIG-Content | labels: content, core |
| [o3de#19900](https://github.com/o3de/o3de/pull/19900) | Fix LuaIDE crash on exit (double free). | SIG-Content | labels: content, core |
| [o3de#19908](https://github.com/o3de/o3de/pull/19908) | Changed button from home to tilde. | SIG-Content | labels: content, core |
| [o3de#19951](https://github.com/o3de/o3de/pull/19951) | Remove Support for CryEngine Plugins | SIG-Content | labels: content, core |
| [o3de#19954](https://github.com/o3de/o3de/pull/19954) | Allows for Template Inheritance in the template system | SIG-Content | labels: content, core |
| [o3de#19998](https://github.com/o3de/o3de/pull/19998) | Replace Git-Based FetchContent Patching with patch-ng | SIG-Content | labels: content, core |
| [o3de#19729](https://github.com/o3de/o3de/pull/19729) | \[Wayland\] Allow Qt tools to force XCB. | SIG-Graphics-Audio | labels: graphics-audio, platform |
| [o3de#19677](https://github.com/o3de/o3de/pull/19677) | Security: Add bounds check on componentInputCount to prevent OOM DoS | SIG-Network | labels: network, security |
