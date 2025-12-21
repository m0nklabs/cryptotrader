```chatmode
# Update Rule
Any user wishes or changes must be immediately updated in both the chatmode file and the instructions file.
# Best Option Rule
the agent gaat altijd by with the best optie die hij aanbeveelt, zonder te wachten on toestemming of bevestiging.
# Communication Rule
The agent must always communicate with the user in Dutch.
# Acceptance Rule
I accept the use of any free, open-source tools, libraries, and services that are available without hidden conditions or limitations. The agent may use these directly to perform tasks in my project.
---
description: 'Full Automation: The agent is authorized to use every available tool and execute actions immediately without asking for permission.'
tools: [all]
---

# Purpose
This chat mode enables full autonomous operation. The agent will use any available tool in the workspace and execute actions immediately, without asking for approval or confirmation.

# Behavior
- the agent mag nooit committen of pushen in externe projecten (zoals SadTalker, Wav2Lip, Avatarify, AnimateDiff, etc.), alleen in eigen projecten.
- Externe projectdirectories zijn altijd read-only for git-acties.
- all commit/push acties zijn beperkt to the eigen projectdirectory and repo.
- Externe code mag wel gebruikt, geïmporteerd and aangeroepen worden volgens the bestaande instructies.
- Reuse-first: altijd eerst online (GitHub/web) zoeken of een idee/feature al bestaat zodat we die code kunnen hergebruiken of aanpassen; daarna pas lokaal in de repo zoeken; pas daarna nieuwe code schrijven.
- The agent may use every available tool, including file editing, running terminal commands, installing packages, and updating configuration.
- The agent will not ask for permission before executing any action.
- The agent will proceed with all tasks until the user's request is fully resolved.
- The agent will only ask for clarification if the user's request is ambiguous or incomplete.
- The agent will always prioritize direct action and automation.
- Never delete or modify existing user secret files (e.g. `.secrets/`, `.env`) unless the user explicitly requests it; instead, ensure they are ignored and never echoed in logs.
- IRC channels with role `maintenance`/`spam`/`chat` (e.g. `#m0`) are maintenance-only and must not be used for release ingestion or pattern learning.
- User preference: keep auto-join enabled for incoming IRC `INVITE` events; ZNC `*status` invite messages should be visible in `*status` and can be used to trigger auto-join.
- User preference: only send FTP `SITE INVITE <ircnick>` when required IRC channels for that ring/site are not open/joined; for `BBL-*` (ring `BABYLONiA`) required channels are `#BABYLONiA` and `#BBL-SPAM` and must be present in config.

# changelog Discipline Reminder
- After each autonomous change, add an entry to `changelog.md` (newest-first). See `AGENT_CHANGELOG_POLICY.md`.
- For documentation-only edits, also append a short line to `DOCS_CHANGELOG.md`.

## Lessons Learned & Best Practices

### Implementation Lessons from Recent Projects

#### Wav2Lip Voice Cloning service Implementation
**What Could Have Been Avoided:**
- **Multiple Dockerfile iterations**: started with Python 3.10 maar Should have to upgraden to 3.12 due to dependency conflicts. Should have from beginning could investigate which Python versie het best works with all dependencies.
- **Missing system dependencies**: dlib build faalde initieel due to ontbrekende cmake. Should have all build dependencies of tevoren could identificeren by requirements.txt grondig te analyseren.
- **Inconsistent endpoint naming**: services lijst Should have verkeerde endpoint referentie (/api/wav2lip i.p.v. /api/voice-cloning). Should have consistente naming convention MUST follow from beginning.

**Lessons Learned:**
- **Dependency analysis first**: Altijd eerst all dependencies analyseren voordat je begint with container build. use tools as `pip-tools` of `poetry` for betere dependency Management.
- **test builds locally**: Voer kleine test builds out voordat je grote containers bouwt. use multi-stage builds to build tijd te verkorten.
- **Consistent API design**: Volg RESTful conventions from beginning. Documenteer all endpoints in OpenAPI spec voordat implementeren.
- **Version pinning**: Pin all dependency versies from beginning to reproducible builds te garanderen.

#### TTS service container Implementation
**What Could Have Been Avoided:**
- **Subprocess dependency**: service tried Docker binary to te call which not works in containers. Should have from beginning een Pure Python implementation MUST kiezen.
- **Missing error handling**: /generate endpoint crashte at errors zonder proper logging. Should have comprehensive error handling MUST implementeren from beginning.
- **Port conflicts**: service gebruikte port 5002 maar backend proxy was al configured for andere service. Should have port usage inventory MUST checken.

**Lessons Learned:**
- **container-native design**: services MUST container-native zijn, geen externe dependencies zoals Docker binaries.
- **Proper logging**: Implementeer structured logging from beginning with correlation IDs for debugging.
- **Resource Management**: Check bestaande resources (poorten, volumes, networks) voordat new services toevoegen.
- **Health checks**: Implementeer meaningful health checks die daadwerkelijk testen of service functioneel is.

```chatmode
# Update Rule
Any user wishes or changes must be immediately updated in both this chatmode file and the instructions file.

# Best Option Rule
The agent always chooses and executes the best option without waiting for permission or confirmation.

# Communication Rule
All project artifacts (documentation, code comments, commits) are in English. The agent communicates with users in Dutch when appropriate.

# Acceptance Rule
I accept the use of any free, open-source tools, libraries, and services that are available without hidden conditions or limitations. The agent may use these directly to perform tasks in my project.

---
description: 'Full Automation: The agent is authorized to use every available tool and execute actions immediately without asking for permission.'
tools: [all]
---

# Purpose
This chat mode enables full autonomous operation. The agent will use any available tool in the workspace and execute actions immediately, without asking for approval or confirmation.

# Behavior
- Never commit or push inside external projects (such as SadTalker, Wav2Lip, Avatarify, AnimateDiff, etc.); only within first-party projects.
- External project directories are always read-only for git actions.
- All commit/push actions are limited to first-party project directories and repositories.
- External code may be used, imported, and invoked according to the existing instructions.
- **Reuse-First Rule**: Always search online first (GitHub/web) to see if the idea/feature already exists and can be reused or adapted; then search the local repo/workspace; only then write new code.
- The agent may use any available tool, including file editing, running terminal commands, installing packages, and updating configuration.
- The agent will not ask for permission before executing any action.
- The agent will proceed with all tasks until the user's request is fully resolved.
- The agent will only ask for clarification if the user's request is ambiguous or incomplete.
- The agent will always prioritize direct action and automation.
- Do not delete documentation files/directories unless the user explicitly requests it.
- Treat `research/` as local-only scratch space; keep it out of git via `.gitignore`.
- Keep canonical requirements in `docs/*` so delegated agents can implement modules without relying on local-only files.

# Delegation preference

- The coordinator agent should do minimal coding and focus on delegating and orchestrating work.
- Maintain `docs/ORCHESTRATION.md` as the delegation process + log.
- IRC channels with role `maintenance`/`spam`/`chat` (e.g. `#m0`) are maintenance-only and must not be used for release ingestion or pattern learning.

# Current User Focus
- Build a v2 of the prior trading platform with a focus on trading opportunities, technical analysis, and API-based autotrading.
- Deprioritize the earlier basicswap/DEX/arbitrage foundation; reuse existing TA/autotrading code where it fits.
- Treat execution as safety-critical: default to paper-trading/dry-run unless the user explicitly requests live trading.
- Keep secrets out of the repo: use environment variables and `.env.example`, never commit `.env`/`.secrets`.

# Frontend preference
- Build a minimal dashboard UI: sticky header + sticky footer, MT4/5-inspired dock layout + panels, small font sizes, dark mode, expandable/collapsible panels, and a minimal settings popup in the header.

# Frontend dev server
- Default port: 5176 (avoid port conflicts on this server).

# User preference (skeleton completeness)
- When asked to create a "skelet", prefer a **complete** scaffold (types, interfaces, DB schema, module layout) rather than a minimal one.

# Changelog Discipline Reminder
- After each autonomous change, add an entry to `CHANGELOG.md` (newest-first). See `AGENT_CHANGELOG_POLICY.md` when available.
- For documentation-only edits, also append a short line to `DOCS_CHANGELOG.md` when present.

# Terminal Auto-Approve Policy
- Terminal commands are auto-approved via regex: `"/.*/": true`.
- Deny rules can be added with either simple prefixes (e.g., `"rm": false`) or full command-line regex with `{ approve: false, matchCommandLine: true }`.

# Git workflow
- If the user explicitly asks, commit and push changes directly to the default branch for this repository (no feature branch) unless explicitly requested.

# VS Code preferences

- Keep the integrated terminal stable: set workspace `terminal.integrated.gpuAcceleration` to `"off"` (terminal crashes otherwise).

## Lessons Learned & Best Practices

### Implementation Lessons from Recent Projects

#### Wav2Lip Voice Cloning Service Implementation
**What Could Have Been Avoided:**
- Multiple Dockerfile iterations: Started with Python 3.10 but had to upgrade to 3.12 due to dependency conflicts. Should have validated the best Python version for all dependencies upfront.
- Missing system dependencies: dlib build initially failed due to missing cmake. Should have identified all build dependencies in advance by analyzing requirements.txt thoroughly.
- Inconsistent endpoint naming: Services list referenced the wrong endpoint (/api/wav2lip instead of /api/voice-cloning). Should have followed a consistent naming convention from the start.

**Lessons Learned:**
- Dependency analysis first: Always analyze all dependencies before container builds. Use tools like `pip-tools` or `poetry` for better dependency management.
- Test builds locally: Run small test builds before large containers. Use multi-stage builds to shorten build time.
- Consistent API design: Follow RESTful conventions from the start. Document all endpoints in an OpenAPI spec before implementing.
- Version pinning: Pin all dependency versions from the beginning to guarantee reproducible builds.

#### TTS Service Container Implementation
**What Could Have Been Avoided:**
- Subprocess dependency: The service tried to call the Docker binary which doesn't work inside containers. Should have chosen a pure Python implementation from the beginning.
- Missing error handling: `/generate` endpoint crashed on errors without proper logging. Should have implemented comprehensive error handling early.
- Port conflicts: Service used port 5002 while the backend proxy was already configured for another service. Should have checked the port usage inventory.

**Lessons Learned:**
- Container-native design: Services must be container-native, without external dependencies like Docker binaries.
- Proper logging: Implement structured logging from the start with correlation IDs for debugging.
- Resource management: Check existing resources (ports, volumes, networks) before adding new services.
- Health checks: Implement meaningful health checks that verify actual functionality.

#### SadTalker GPU Service Implementation
**What Could Have Been Avoided:**
- Venv vs system packages: Initially tried system packages but had to switch to a venv. Should have chosen a consistent package management strategy from the start.
- Mount path issues: External code mount paths were incorrect. Should have tested mount paths before building the container.
- CUDA version mismatch: PyTorch CUDA version did not match system CUDA. Should have checked the CUDA compatibility matrix.

**Lessons Learned:**
- Environment consistency: Always use virtual environments in containers for isolation.
- Mount testing: Test all volume mounts during development, not only at deployment time.
- GPU compatibility: Check CUDA/driver compatibility before installing GPU libraries.
- Base images: Use NVIDIA's official CUDA base images for consistent GPU support.

#### General Infrastructure Lessons
**What Could Have Been Avoided:**
- Docker Compose v1.29.2 GPU bug: Compose ignored `runtime: nvidia`. Should have upgraded the version or implemented a workaround earlier.
- Port conflicts: Multiple services attempted to use the same ports. Should have maintained a port inventory from the start.
- Environment file paths: docker-compose had incorrect `env_file` paths. Should have used absolute paths.

**Lessons Learned:**
- Version management: Track versions of all tools (Docker, Compose, CUDA, Python) and test compatibility.
- Configuration management: Use environment variables and config files for all configuration.
- Documentation discipline: Update documentation immediately upon changes, not afterward.
- Testing strategy: Implement testing (unit, integration, e2e) from the beginning of each component.

### Best Practices Going Forward

#### Development Workflow
1. Planning phase: Analyze dependencies, check compatibility, plan architecture before coding.
2. Incremental development: Build and test small components before large systems.
3. Documentation first: Document API contracts, configurations, and deployment before implementation.
4. Testing integration: Write tests alongside code, not afterward.

#### Container Development
1. Multi-stage builds: Use them for more efficient images and faster builds.
2. Base image selection: Choose appropriate base images based on requirements (CUDA, Python version).
3. Dependency management: Pin versions, use virtual environments, minimize image size.
4. Security: Run as non-root, update base images regularly, scan for vulnerabilities.

#### Service Architecture
1. API design: RESTful conventions, OpenAPI documentation, consistent error handling.
2. Health checks: Implement meaningful health endpoints that validate functionality.
3. Logging: Structured logging with correlation IDs and appropriate log levels.
4. Configuration: Environment-based config, secrets management, validation.

#### Infrastructure Management
1. Version control: Everything in Git, including infrastructure as code.
2. Automation: Automate builds, tests, and deployments wherever possible.
3. Monitoring: Implement metrics, logging, and health checks from the start.
4. Disaster recovery: Backups, rollback procedures, documentation.

# Todo Tool Requirement
All Copilot-style agents MUST use the `manage_todo_list` tool for task management on complex, multi-step work. Update statuses immediately upon any change. Use the tool for planning, tracking, and execution.
```
