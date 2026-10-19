The O3DE 26.10 release moves the Editor onto Qt 6, adds experimental support for Apple Silicon, and brings a season of work on robotics simulation to the ROS 2 and SimulationInterfaces gems. It also carries more than two hundred fixes and smaller improvements across the engine.

Here are the notable [highlights](#highlights) for this release. For a comprehensive breakdown, jump to the [full list of changes](#full-list-of-changes), which is organized by Special Interest Group (SIG) and includes links to the relevant Pull Requests (PRs). A short list of [known issues](#known-issues) follows the highlights.

To start using O3DE 26.10, follow the steps on the [Get Started](https://docs.o3de.org/docs/welcome-guide/setup/) page. Then, you can start building a new project choosing from one of the [provided templates](https://docs.o3de.org/docs/learning-guide/samples/templates/), or explore a pre-made example for [games](https://docs.o3de.org/docs/learning-guide/samples/advanced/) or [robotics](https://docs.o3de.org/docs/learning-guide/samples/robotic).

# Highlights

- **The Editor runs on Qt 6**. The Editor and all of its tools now build against a standard Qt 6.10.2, replacing the custom Qt 5.15.2 build that O3DE had carried since its first release. Qt 5 is no longer maintained by its authors, so this keeps the Editor on a toolkit that still receives security fixes. The upgrade came with several months of follow-up work: the Entity Inspector was reworked, keyboard shortcuts are now consistent across the Inspector, Outliner, Asset Editor and LyShine, the Asset Editor gained undo, and a long list of crashes, docking and styling regressions found during testing were fixed.

- **Experimental support for Apple Silicon**. O3DE now builds natively for Mac ARM64, and macOS builds no longer require Apple's Clang. Treat this as experimental for 26.10.

- **Linux window systems and the web**. On Linux, the game launcher has initial Wayland support and can switch between X11 and Wayland at build or run time. The Editor still runs through X11 or XWayland; see the known issues. Separately, configuration files for the Emscripten compiler lay the groundwork for a future WebAssembly target.

- **Robot Importer, reworked**. The ROS 2 Robot Importer gem has been restructured around an import session that tracks the assets a robot description references and reports build status as it goes. Its parsing code now lives in one place, duplicated asset handling has been consolidated, and files and functions still named for URDF have been renamed now that the gem parses SDF. libsdformat moves to 16.0.1.

- **SimulationInterfaces keeps pace with ROS 2**. The gem supports the simulation_interfaces 2.1.0 package that ships with ROS 2 Lyrical Luth, alongside versions 1.4 through 1.6. It adds the SpawnEntities service for spawning several entities in one call, notifies when entities are spawned, rejects invalid poses instead of producing undefined results, and removes simulated entities before a level unloads. The ROS 2 camera can now publish compressed images.

- **Physics for robots**. ArticulationLink computes its inertia tensor automatically from mass and shape, which removes a long-standing mismatch in joint-chain behaviour between O3DE and Isaac Sim. PhysX gains an enhanced-determinism option, and the removal of PhysX 4 is complete. DetourCrowd joins the Recast Navigation integration, giving agents collision avoidance and smooth steering.

- **Rendering**. Ground Truth Ambient Occlusion is available as an alternative to SSAO, following the [SIG-Graphics-Audio RFC](https://github.com/o3de/sig-graphics-audio/blob/main/rfcs/GTAOIntegration/Proposed%20RFC%20Feature%20GTAO%20%28Ground-Truth%20based%20Ambient%20Occlusion%29.md). Unlit materials gain cutout and blended opacity, double-sided rendering, optional shadows and a billboard mode. Decals render correctly on metallic surfaces and can set a maximum draw distance. The AZSL shader compiler now lives in the engine source tree and builds as a host tool, so every platform compiles the same compiler.

- **Creating components and projects**. The Class Wizard can target any project or Gem and any build target, and it generates basic, level, system and LyShine components as well as data assets. Project templates can inherit from one another, and a new GameplayGem template scaffolds component controllers with their buses, reflection and unit tests. Levels can be loaded from and saved to Gem asset directories, not only the project.

- **A smaller, more standard core**. AZStd::move, array, span and pair now alias their standard library counterparts, and C++20 concepts replace the old SFINAE machinery across AZStd. The Sandbox plugin system inherited from CryEngine is gone in favour of Gems, and the first pass of legacy Cry cleanup has landed. The engine builds under C++23 and C++26, and third-party dependencies fetched with FetchContent now share a download cache across build configurations.

# Known issues

- **Linux only: the Editor crashes at startup if forced onto native Wayland** with `QT_QPA_PLATFORM=wayland` ([o3de#19835](https://github.com/o3de/o3de/issues/19835)). It is not specific to one GPU vendor; it has been seen on NVIDIA and AMD. The 26.10 Editor builds support X11 and XWayland only; on a Wayland desktop the Editor uses XWayland automatically, so leave `QT_QPA_PLATFORM` unset or set it to `xcb`. Windows and macOS are not affected.

  If you build the engine yourself, you can enable native Wayland by configuring with `-DPAL_TRAIT_LINUX_WINDOW_MANAGER_WAYLAND=ON`, leaving the XCB option at its default, after cherry-picking [o3de#20204](https://github.com/o3de/o3de/pull/20204), a one-line fix on `development` that lets the option compile on 26.10. The build needs the Wayland headers, the Wayland protocol files and xkbcommon (on Fedora, `wayland-devel`, `wayland-protocols-devel` and `libxkbcommon-devel`); the bundled Qt already includes its Wayland plugin. Treat the result as experimental: the Editor runs as a Wayland client, but the Material Editor and other Atom tools crash, the window cannot be moved by its title bar ([o3de#19820](https://github.com/o3de/o3de/issues/19820)), and the viewport can be drawn at the wrong size after a resize. Native Wayland support is tracked in [o3de#18513](https://github.com/o3de/o3de/issues/18513).

- **DX12 can crash on shutdown** from a descriptor heap being released twice. Fixed in `development` ([o3de#20141](https://github.com/o3de/o3de/pull/20141)).
- **Terrain can flicker on Vulkan** from bindless texture indexing; DX12 is not affected. A fix is in review for `development` ([o3de#20161](https://github.com/o3de/o3de/pull/20161)).

# Thank you

Thank you to everyone who contributed code, reviews, issues, testing and discussion to 26.10.0. None of this happens without you.
