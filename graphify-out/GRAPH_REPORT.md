# Graph Report - .  (2026-11-03)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 4192 nodes · 8674 edges · 221 communities (210 shown, 11 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 169 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `27e02290`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- archify.mjs
- check-update.mjs
- render-erd.mjs
- geometry.mjs
- render-class.mjs
- workflow-compiler.mjs
- generated-validators.mjs
- architecture-delta.mjs
- render-sequence.mjs
- visual-check.mjs
- render-lifecycle.mjs
- atomic-output.mjs
- render-architecture.mjs
- YAYTP6L5.js
- 42UTT654.js
- render-waterfall.mjs
- render-timeline.mjs
- properties
- UKSIWDDN.js
- finalize.mjs
- i18n.mjs
- properties
- properties
- brand-marks.mjs
- path-semantics.mjs
- render-tree.mjs
- run.py
- id
- properties
- L4LY553T.js
- properties
- properties
- check-render-output.mjs
- scripts
- func3
- properties
- properties
- id
- output-path.mjs
- preview.mjs
- render.mjs
- diagramType
- $defs
- route-quality.mjs
- escapeHtml
- properties
- EEIX5ZYH.js
- properties
- properties
- properties
- enum
- enum
- properties
- properties
- properties
- properties
- diagrams.mjs
- reader.js
- validateArchitecture
- enum
- validatePortablePath
- repository
- properties
- properties
- properties
- properties
- sources.mjs
- workflow-v2.mjs
- class.schema.json
- properties
- required
- parseAttrs
- throwDiagnosticError
- properties
- $defs
- properties
- explainer.schema.json
- required
- properties
- properties
- XTDUIGUI.js
- UPTXNAXN.js
- properties
- required
- properties
- properties
- validate.mjs
- diagnostics.mjs
- properties
- properties
- properties
- $ref
- browser-check.mjs
- prepare.mjs
- cli.mjs
- required
- enum
- properties
- properties
- desktop-readability.mjs
- required
- properties
- properties
- properties
- properties
- properties
- enum
- properties
- generate-brand-marks.mjs
- owned-temp-directory.mjs
- scenarios.mjs
- layout
- waterfall.schema.json
- workflow.schema.json
- entries
- entries
- required
- enum
- entries
- required
- properties
- legendEntry
- required
- semanticRelation
- generate-validators.mjs
- $ref
- answer
- image
- entries
- entries
- items
- entries
- translations
- enum
- enum
- tree.schema.json
- items
- PipeCdp
- wraps
- enum
- required
- properties
- facts
- layout
- collectNonFiniteAttrs
- parse.mjs
- enum
- inline.mjs
- meta
- size
- viewBox
- col
- portableOutputPath
- enum
- enum
- enum
- mainPath
- meta
- sequence.schema.json
- meta
- enum
- meta
- enum
- meta
- enum
- meta
- viewBox
- delivery-update.mjs
- svg-path-analysis.mjs
- layout
- enum
- focus
- required
- layout
- meta
- enum
- required
- enum
- render-examples.mjs
- validate45
- enum
- row
- via
- stages
- width
- col
- via
- viewBox
- width
- timezone
- enum
- bias
- fromCol
- validate20
- col
- height
- label
- at
- row
- stage
- labelSegment
- label
- title
- to
- duration
- height
- toCol
- width
- manifest.json
- classification
- icon
- id
- sources
- sublabel
- run.sh script
- setup.sh
- label
- labelSegment
- from
- labelAt

## God Nodes (most connected - your core abstractions)
1. `compileWorkflowInternal()` - 81 edges
2. `asArray()` - 76 edges
3. `textUnits()` - 65 edges
4. `escapeHtml()` - 58 edges
5. `commandDeliver()` - 47 edges
6. `func3()` - 39 edges
7. `translateMessage()` - 39 edges
8. `throwDiagnosticError()` - 34 edges
9. `rectsOverlap()` - 34 edges
10. `runBrowserEvidence()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `de()` --indirect_call--> `Ge()`  [INFERRED]
  .agents/skills/archify/explainer/vendor/pele/chunks/YAYTP6L5.js → .agents/skills/archify/explainer/vendor/pele/chunks/UKSIWDDN.js
- `consolidateDiagnostics()` --indirect_call--> `diagnostic()`  [INFERRED]
  .agents/skills/archify/bin/finalize.mjs → .agents/skills/archify/bin/archify.mjs
- `cleanupStagedEvidence()` --indirect_call--> `identity()`  [INFERRED]
  .agents/skills/archify/bin/visual-check.mjs → .agents/skills/archify/bin/finalize.mjs
- `redactDiagnostic()` --indirect_call--> `absolutePath()`  [INFERRED]
  .agents/skills/archify/bin/preview.mjs → .agents/skills/archify/renderers/shared/path-semantics.mjs
- `stagePreviewCommit()` --calls--> `removeOwnedRegularFile()`  [EXTRACTED]
  .agents/skills/archify/bin/preview.mjs → .agents/skills/archify/renderers/shared/atomic-output.mjs

## Import Cycles
- None detected.

## Communities (221 total, 11 thin omitted)

### Community 0 - "archify.mjs"
Cohesion: 0.06
Nodes (120): acquireDeliveryLock(), artifactCheckMaxBuffer(), artifactIdentity(), assertDeliveryOwnership(), assertOwnedDeliveryLock(), beginDeliveryAttempt(), canonicalExistingDeliveryOutput(), captureDeliveryTargetState() (+112 more)

### Community 1 - "check-update.mjs"
Cohesion: 0.05
Nodes (111): acquireOperation(), assertBoundedRegularFile(), assertCacheTargetAbsent(), assertRenameableCacheEntry(), assertSafeCacheEntry(), assertSafeDirectory(), assertSafeRegularFile(), cacheMkdir() (+103 more)

### Community 2 - "render-erd.mjs"
Cohesion: 0.04
Nodes (91): buildLayoutReport(), hasAutomaticRouteGeometry(), renderConnectionPath(), bandedLayout(), DEFAULT_ER_GRID, entityHeight(), erGridLayout(), gridColumn() (+83 more)

### Community 3 - "geometry.mjs"
Cohesion: 0.07
Nodes (84): busRouteConflict(), nodeTextFit, crossingCount(), distance(), length(), masks(), pinned(), related() (+76 more)

### Community 4 - "render-class.mjs"
Cohesion: 0.05
Nodes (72): createRouter(), attributeText(), autoViewBox(), bands, buildLayoutReport(), busGroups, busPaths, cliArgs (+64 more)

### Community 5 - "workflow-compiler.mjs"
Cohesion: 0.07
Nodes (69): boundaryRect(), entityHeader(), fonts(), preferredWidth(), validateStructure(), automaticCanvasWidth(), participantSpreadGeometry(), spreadColumnGeometry() (+61 more)

### Community 6 - "generated-validators.mjs"
Cohesion: 0.03
Nodes (73): pattern10, pattern11, pattern12, pattern13, pattern133, pattern14, pattern15, pattern16 (+65 more)

### Community 7 - "architecture-delta.mjs"
Cohesion: 0.07
Nodes (66): addNodeMarker(), addState(), annotateArchitectureSideSvg(), architectureDeltaChangeRows(), ArchitectureDeltaError, BOUNDARY_FIELDS, boundaryChangeMap(), boundaryElements() (+58 more)

### Community 8 - "render-sequence.mjs"
Cohesion: 0.07
Nodes (62): autoViewBox(), arrowClass, automaticHeight, compositionFrames, contentBottom, __dirname, layout, legacySegmentLabelBox() (+54 more)

### Community 9 - "visual-check.mjs"
Cohesion: 0.08
Nodes (57): appendEvidenceCleanupWarning(), appendEvidencePublicationFailure(), baseReceipt(), beginVisualEvidenceWrite(), CAPTURE_VIEWPORTS, CHROME_NO_SANDBOX_ENV, CHROME_STARTUP_TIMEOUT_MS, cleanupStagedEvidence() (+49 more)

### Community 10 - "render-lifecycle.mjs"
Cohesion: 0.05
Nodes (57): assignArcLevels(), assignTracks(), bracketOf, brackets, bracketTargets, canvasWidth, countCrossings(), depth (+49 more)

### Community 11 - "atomic-output.mjs"
Cohesion: 0.13
Nodes (52): captureOwnedDeliverySidecars(), args, backupOwnedPublishedEntry(), restoreOwnedBackup(), unlinkOwnedEntry(), backupPublicRegularFileBinding(), captureAtomicOutput(), captureRegularFileBinding() (+44 more)

### Community 12 - "render-architecture.mjs"
Cohesion: 0.06
Nodes (47): DEFAULT_GRID, gridLayout(), resolveComponentPos(), validateGridPlacement(), architectureLegendEntries, autoViewBoxFor(), boundaryLabelWidth(), cliArgs (+39 more)

### Community 13 - "YAYTP6L5.js"
Cohesion: 0.11
Nodes (46): A(), b(), d(), E(), indent(), k(), L(), N() (+38 more)

### Community 14 - "42UTT654.js"
Cohesion: 0.10
Nodes (44): addClass(), addPoint(), B(), ct(), Ht(), Kt(), parse(), qt() (+36 more)

### Community 15 - "render-waterfall.mjs"
Cohesion: 0.04
Nodes (43): axisLabels, byId, children, cliArgs, details, { diagram: wf, template, outPath, sourceEvidence }, __dirname, dotX() (+35 more)

### Community 16 - "render-timeline.mjs"
Cohesion: 0.06
Nodes (43): breaks, buildLayoutReport(), cards, cliArgs, clockLabel(), { diagram: tl, template, outPath, sourceEvidence }, __dirname, durationLabel() (+35 more)

### Community 17 - "properties"
Cohesion: 0.05
Nodes (44): $ref, $ref, $ref, $ref, $ref, properties, $ref, type (+36 more)

### Community 18 - "UKSIWDDN.js"
Cohesion: 0.11
Nodes (41): hash(), hash(), D(), expect(), fail(), H(), j(), S() (+33 more)

### Community 19 - "finalize.mjs"
Cohesion: 0.11
Nodes (42): allChecksPassed(), browserEvidence(), captureReceipt(), compactFinalizeReceipt(), consolidateDiagnostics(), defaultFinalizeReceiptPath(), defaultFinalizeSummaryPath(), defaultRunner() (+34 more)

### Community 20 - "i18n.mjs"
Cohesion: 0.09
Nodes (41): componentContext(), BUNDLED_CATALOGS, bundledCatalog(), bundledLocaleFor(), CANONICAL_KEYS, CANONICAL_PLACEHOLDERS, catalogFor(), classifyTranslations() (+33 more)

### Community 21 - "properties"
Cohesion: 0.05
Nodes (44): $ref, additionalProperties, properties, type, output, title, additionalProperties, properties (+36 more)

### Community 22 - "properties"
Cohesion: 0.05
Nodes (40): $ref, type, type, maximum, minimum, type, $ref, $ref (+32 more)

### Community 23 - "brand-marks.mjs"
Cohesion: 0.10
Nodes (38): commandBrands(), asUrl(), BASIC_HTML_REFERENCES, beforeDeadline(), captureBrandReference(), captureRemoteBrand(), captureTimeoutMilliseconds(), checkedFetch() (+30 more)

### Community 24 - "path-semantics.mjs"
Cohesion: 0.15
Nodes (39): visualEvidenceOwnershipMatches(), absolutePath(), compareFutureLocations(), compareKnownEntries(), compareUnmaterializedNames(), containedBy(), futureWindowsNameRisk(), hasStableIdentity() (+31 more)

### Community 25 - "render-tree.mjs"
Cohesion: 0.07
Nodes (36): nodeTextFit, all, ancestorsOf(), attachOf(), bandSize, bandStart, centerOf(), childrenOf (+28 more)

### Community 26 - "run.py"
Cohesion: 0.08
Nodes (35): Agent, main(), execute_task(), list_workspace_files(), main(), Run a single autonomous task from CLI arguments and exit., List relative file paths in the workspace directory., Execute a single coding prompt through the agent with streaming output. (+27 more)

### Community 27 - "id"
Cohesion: 0.09
Nodes (34): $ref, additionalProperties, properties, type, $ref, properties, properties, additionalProperties (+26 more)

### Community 28 - "properties"
Cohesion: 0.07
Nodes (38): items, maxItems, minItems, type, items, additionalProperties, items, maxItems (+30 more)

### Community 29 - "L4LY553T.js"
Cohesion: 0.13
Nodes (31): f(), l(), t(), u(), st(), addPlot(), Je(), K() (+23 more)

### Community 30 - "properties"
Cohesion: 0.05
Nodes (40): $ref, type, $ref, $ref, type, properties, minLength, type (+32 more)

### Community 31 - "properties"
Cohesion: 0.06
Nodes (35): type, additionalProperties, properties, required, type, $defs, attribute, method (+27 more)

### Community 32 - "check-render-output.mjs"
Cohesion: 0.08
Nodes (22): checks, collectLegendCollisions(), collectRelationshipCrossings(), composition, crossProduct(), htmlPath, onSegment(), orientation() (+14 more)

### Community 33 - "scripts"
Cohesion: 0.06
Nodes (33): bin, archify, description, devDependencies, ajv, simple-icons, engines, node (+25 more)

### Community 34 - "func3"
Cohesion: 0.10
Nodes (34): func3(), validate27(), validate28(), validate30(), validate31(), validate33(), validate34(), validate36() (+26 more)

### Community 35 - "properties"
Cohesion: 0.07
Nodes (34): items, guidedViews, sourceReferences, minimum, type, items, maxItems, type (+26 more)

### Community 36 - "properties"
Cohesion: 0.06
Nodes (33): $ref, $ref, $ref, properties, minLength, type, $ref, type (+25 more)

### Community 37 - "id"
Cohesion: 0.09
Nodes (33): required, additionalProperties, required, type, required, required, chart, diff (+25 more)

### Community 38 - "output-path.mjs"
Cohesion: 0.12
Nodes (28): defaultDeliveryPaths(), bytes, candidate, capture, inputPath, { outputPath }, request, sourceText (+20 more)

### Community 39 - "preview.mjs"
Cohesion: 0.10
Nodes (28): failureDetails(), launchTarget(), launchTimeout(), openArtifact(), OPENERS, openLoopbackUrl(), atomicOutputError(), atomicOutputFailure() (+20 more)

### Community 40 - "render.mjs"
Cohesion: 0.12
Nodes (21): checkExplainerHtml(), decode(), decodeURIComponentSafe(), isExplainerHtml(), scanHtml(), layoutExplainerPanels(), packPageBundle(), swap() (+13 more)

### Community 41 - "diagramType"
Cohesion: 0.08
Nodes (31): meta, required, meta, required, meta, schema_version, required, meta (+23 more)

### Community 42 - "$defs"
Cohesion: 0.06
Nodes (30): enum, oneOf, type, $defs, animation, brandMark, cards, id (+22 more)

### Community 43 - "route-quality.mjs"
Cohesion: 0.13
Nodes (26): boundsForPoints(), boundsForRects(), cleanRouteDetourProblems(), collinearOverlap(), DEFAULTS, emptyControlPointClearance(), expandedRect(), MinHeap (+18 more)

### Community 44 - "escapeHtml"
Cohesion: 0.18
Nodes (29): renderBoundaryFrame(), renderBoundaryLabel(), renderComponent(), renderSvg(), renderRelationshipPath(), renderSvg(), renderType(), renderEntity() (+21 more)

### Community 45 - "properties"
Cohesion: 0.07
Nodes (28): $ref, type, type, $ref, properties, type, type, minimum (+20 more)

### Community 46 - "EEIX5ZYH.js"
Cohesion: 0.14
Nodes (25): addStyleData(), addSubsetData(), addTextData(), bt(), color(), Ct(), dt(), et() (+17 more)

### Community 47 - "properties"
Cohesion: 0.07
Nodes (28): $ref, $ref, properties, type, animation, locale, output, quality_profile (+20 more)

### Community 48 - "properties"
Cohesion: 0.09
Nodes (22): $ref, $ref, properties, type, animation, locale, output, quality_profile (+14 more)

### Community 49 - "properties"
Cohesion: 0.07
Nodes (28): $ref, $ref, properties, type, animation, locale, output, quality_profile (+20 more)

### Community 50 - "enum"
Cohesion: 0.07
Nodes (29): $ref, diagram, additionalProperties, oneOf, properties, required, type, enum (+21 more)

### Community 51 - "enum"
Cohesion: 0.11
Nodes (26): enum, componentType, active, decision, external, failure, neutral, start (+18 more)

### Community 52 - "properties"
Cohesion: 0.08
Nodes (26): $ref, $ref, type, $ref, $ref, properties, minLength, type (+18 more)

### Community 53 - "properties"
Cohesion: 0.08
Nodes (25): $ref, enum, $ref, properties, $ref, animation, engineering_profile, locale (+17 more)

### Community 54 - "properties"
Cohesion: 0.07
Nodes (29): $ref, $ref, $ref, $ref, additionalProperties, properties, type, type (+21 more)

### Community 55 - "properties"
Cohesion: 0.08
Nodes (25): $ref, $ref, properties, $ref, animation, locale, output, quality_profile (+17 more)

### Community 56 - "diagrams.mjs"
Cohesion: 0.18
Nodes (22): attrs(), changesPreview(), compileExplainerDiagram(), decode(), duplicateCheck(), fail(), freezeBytes(), inferredId() (+14 more)

### Community 57 - "reader.js"
Cohesion: 0.15
Nodes (20): applyTheme(), cropDiagramPreviews(), ensureDiagramReadability(), exportImage(), fitDiagrams(), fitLaneFrames(), layoutBoard(), linkTerms() (+12 more)

### Community 58 - "validateArchitecture"
Cohesion: 0.18
Nodes (23): componentDiagnosticBox(), rectContains(), validateArchitecture(), compileDataflow(), __dirname, loadDiagramWithBrandMarks(), recordDiagnostic(), cleanAmbiguousCorridorProblems() (+15 more)

### Community 59 - "enum"
Cohesion: 0.09
Nodes (24): auto, route, enum, auto, route, enum, auto, bottom-channel (+16 more)

### Community 60 - "validatePortablePath"
Cohesion: 0.15
Nodes (22): architecture(), classDiagram(), dataflow(), erd(), lifecycle(), sequence(), timeline(), tree() (+14 more)

### Community 61 - "repository"
Cohesion: 0.09
Nodes (22): repository, enum, link_mode, provider, revision, url, enum, additionalProperties (+14 more)

### Community 62 - "properties"
Cohesion: 0.09
Nodes (23): items, maxItems, minItems, type, items, maxItems, minItems, type (+15 more)

### Community 63 - "properties"
Cohesion: 0.09
Nodes (22): $ref, $ref, properties, $ref, animation, locale, output, quality_profile (+14 more)

### Community 64 - "properties"
Cohesion: 0.09
Nodes (22): $ref, $ref, properties, type, animation, locale, output, quality_profile (+14 more)

### Community 65 - "properties"
Cohesion: 0.09
Nodes (22): type, minimum, type, $ref, properties, minLength, type, $ref (+14 more)

### Community 66 - "sources.mjs"
Cohesion: 0.23
Nodes (19): chartFromData(), compileExplainerChart(), pieLegend(), fileName(), parseExplainerDiff(), sourceLines(), containsExplainerSecret(), deriveRepository() (+11 more)

### Community 67 - "workflow-v2.mjs"
Cohesion: 0.22
Nodes (18): clone(), diagnostic(), expandableViewBox(), legacyLayoutProbe(), legacyRequirementProbe(), migrateWorkflowDocument(), requiredViewBoxFrom(), result() (+10 more)

### Community 68 - "class.schema.json"
Cohesion: 0.10
Nodes (20): additionalProperties, $ref, const, $id, title, additionalProperties, required, type (+12 more)

### Community 69 - "properties"
Cohesion: 0.10
Nodes (21): $ref, const, minItems, type, items, minItems, type, minItems (+13 more)

### Community 70 - "required"
Cohesion: 0.13
Nodes (21): items, type, items, type, additionalProperties, required, type, id (+13 more)

### Community 71 - "parseAttrs"
Cohesion: 0.18
Nodes (21): collectArchitectureLeadingSpace(), collectArrows(), collectCompositionFrames(), collectLegendBoxes(), collectRelationshipLabelMasks(), collectSequenceColumnSpace(), collectSequenceNoteBorders(), collectUntransformedNodeRects() (+13 more)

### Community 72 - "throwDiagnosticError"
Cohesion: 0.23
Nodes (18): throwAtomicOutputFailure(), throwDiagnosticError(), EVIDENCE_NODE_COLLECTIONS, evidenceFailure(), evidenceNodes(), gitValue(), hasRepositoryEvidence(), prefetchBlobs() (+10 more)

### Community 73 - "properties"
Cohesion: 0.10
Nodes (20): minimum, type, minimum, type, mode, additionalProperties, properties, required (+12 more)

### Community 74 - "$defs"
Cohesion: 0.09
Nodes (23): allOf, properties, required, type, additionalProperties, type, $defs, block (+15 more)

### Community 75 - "properties"
Cohesion: 0.11
Nodes (19): minimum, type, minimum, type, maximum, minimum, type, minimum (+11 more)

### Community 76 - "explainer.schema.json"
Cohesion: 0.14
Nodes (13): additionalProperties, const, $id, additionalProperties, type, properties, diagram_type, meta (+5 more)

### Community 77 - "required"
Cohesion: 0.14
Nodes (19): items, additionalProperties, required, type, from, id, label, to (+11 more)

### Community 78 - "properties"
Cohesion: 0.11
Nodes (19): $ref, $ref, properties, type, animation, locale, output, quality_profile (+11 more)

### Community 79 - "properties"
Cohesion: 0.13
Nodes (15): type, $ref, properties, minLength, type, $ref, detail, id (+7 more)

### Community 80 - "XTDUIGUI.js"
Cohesion: 0.17
Nodes (10): NATIVE, o(), r(), x(), ee(), k(), M(), O() (+2 more)

### Community 81 - "UPTXNAXN.js"
Cohesion: 0.24
Nodes (17): m(), p(), i(), addLink(), be(), de(), $e(), findOrCreateNode() (+9 more)

### Community 82 - "properties"
Cohesion: 0.11
Nodes (17): additionalProperties, $ref, const, minItems, type, $id, properties, cards (+9 more)

### Community 83 - "required"
Cohesion: 0.14
Nodes (18): items, type, items, additionalProperties, allOf, if, required, then (+10 more)

### Community 84 - "properties"
Cohesion: 0.11
Nodes (18): minimum, type, minimum, type, minimum, type, minimum, type (+10 more)

### Community 85 - "properties"
Cohesion: 0.11
Nodes (18): source, items, maxItems, minItems, prefixItems, type, $ref, lines (+10 more)

### Community 86 - "validate.mjs"
Cohesion: 0.21
Nodes (14): at(), EDGE_KEYS, NODE_KEYS, READER_IDS, validateExplainer(), lintExplainerWriting(), proseMask(), RULES (+6 more)

### Community 87 - "diagnostics.mjs"
Cohesion: 0.18
Nodes (15): boundaryKey, fallbackDiagnostic(), formatDiagnostics(), installRendererDiagnosticBoundary(), normalizedDiagnostic(), plainObject(), readerSignal, recorded (+7 more)

### Community 88 - "properties"
Cohesion: 0.12
Nodes (16): additionalProperties, type, $ref, type, const, $id, properties, boundaries (+8 more)

### Community 89 - "properties"
Cohesion: 0.11
Nodes (18): additionalProperties, $ref, const, $id, properties, cards, diagram_type, schema_version (+10 more)

### Community 90 - "properties"
Cohesion: 0.12
Nodes (17): enum, minimum, type, minimum, type, right, properties, minimum (+9 more)

### Community 91 - "$ref"
Cohesion: 0.14
Nodes (17): items, type, items, type, $ref, allowedRoots, allowedTerminals, requiredEdges (+9 more)

### Community 92 - "browser-check.mjs"
Cohesion: 0.26
Nodes (15): activate(), evaluate(), EXPLAINER_VIEWPORTS, explainerObservation(), explainerObservationDiagnostics(), expression(), inspectExplainerBrowser(), inspectNativePreviewLayout() (+7 more)

### Community 93 - "prepare.mjs"
Cohesion: 0.35
Nodes (14): validateExplainerDiagramTarget(), embedded(), fail(), preparePanelPatch(), assertPreparedDependencies(), digest(), fail(), identity() (+6 more)

### Community 94 - "cli.mjs"
Cohesion: 0.22
Nodes (14): applyLocaleTranslations(), isFilesystemError(), loadDiagram(), outputPathGuards, RELATIONSHIP_COLLECTIONS, SEMANTIC_COLLECTIONS, START_TYPES, throwOutputError() (+6 more)

### Community 95 - "required"
Cohesion: 0.16
Nodes (16): items, items, minItems, type, items, additionalProperties, required, type (+8 more)

### Community 96 - "enum"
Cohesion: 0.16
Nodes (16): variant, dashed, default, emphasis, security, enum, dashed, return (+8 more)

### Community 97 - "properties"
Cohesion: 0.13
Nodes (14): additionalProperties, $ref, const, type, $id, properties, cards, diagram_type (+6 more)

### Community 98 - "properties"
Cohesion: 0.12
Nodes (16): $ref, properties, $ref, locale, output, repository, subtitle, title (+8 more)

### Community 99 - "desktop-readability.mjs"
Cohesion: 0.15
Nodes (14): DECLARED_WIDE_READER_CONTRACT, DECLARED_WIDE_READER_MAX_WIDTH, DECLARED_WIDE_READER_RATIO, DECLARED_WIDE_REFERENCE_BODY_HORIZONTAL_PX, DECLARED_WIDE_REFERENCE_DIAGRAM_HORIZONTAL_PX, declaredWideReadabilityBudget(), describeFixedWidthOverflow(), DESKTOP_FIXED_VERTICAL_CHROME_PX (+6 more)

### Community 100 - "required"
Cohesion: 0.16
Nodes (16): items, additionalProperties, required, type, from, id, label, to (+8 more)

### Community 101 - "properties"
Cohesion: 0.13
Nodes (15): properties, enum, kind, unit, x, y, $ref, $ref (+7 more)

### Community 102 - "properties"
Cohesion: 0.13
Nodes (15): metric, $ref, exclusiveMinimum, type, additionalProperties, properties, type, $ref (+7 more)

### Community 103 - "properties"
Cohesion: 0.13
Nodes (14): additionalProperties, $ref, const, $id, type, properties, cards, diagram_type (+6 more)

### Community 104 - "properties"
Cohesion: 0.13
Nodes (15): $ref, const, title, additionalProperties, type, additionalProperties, required, type (+7 more)

### Community 105 - "properties"
Cohesion: 0.14
Nodes (14): $ref, properties, $ref, locale, output, quality_profile, repository, style (+6 more)

### Community 106 - "enum"
Cohesion: 0.14
Nodes (14): enum, callout, chart, code, comparison, diagram, diff, facts (+6 more)

### Community 107 - "properties"
Cohesion: 0.14
Nodes (14): type, $ref, properties, minLength, type, $ref, collapsed, id (+6 more)

### Community 108 - "generate-brand-marks.mjs"
Cohesion: 0.14
Nodes (10): catalog, catalogPath, domains, generated, here, ids, lookupKeys, outputPath (+2 more)

### Community 109 - "owned-temp-directory.mjs"
Cohesion: 0.22
Nodes (7): browserEnvironment(), ChromeVisualBrowser, chromeVisualBrowserArgs(), createOwnedTempDirectory(), directoryIdentity(), retryable, verifyIdentity()

### Community 110 - "scenarios.mjs"
Cohesion: 0.26
Nodes (10): detectGuideLanguage(), formatScenarioList(), listScenarioRecipes(), localized(), normalized(), publicGuideData(), RAW_RECIPES, recommendScenario() (+2 more)

### Community 111 - "layout"
Cohesion: 0.15
Nodes (13): description, enum, auto, none, additionalProperties, properties, type, breaks (+5 more)

### Community 112 - "waterfall.schema.json"
Cohesion: 0.15
Nodes (12): additionalProperties, $ref, const, $id, properties, cards, diagram_type, schema_version (+4 more)

### Community 113 - "workflow.schema.json"
Cohesion: 0.15
Nodes (12): additionalProperties, $defs, side, $id, bottom, left, right, top (+4 more)

### Community 114 - "entries"
Cohesion: 0.17
Nodes (12): additionalProperties, properties, type, grid, additionalProperties, properties, type, enum (+4 more)

### Community 115 - "entries"
Cohesion: 0.17
Nodes (12): additionalProperties, properties, type, grid, additionalProperties, properties, type, enum (+4 more)

### Community 116 - "required"
Cohesion: 0.20
Nodes (12): additionalProperties, required, type, from, id, kind, label, to (+4 more)

### Community 117 - "enum"
Cohesion: 0.17
Nodes (12): class, enum, abstract, aggregation, association, composition, dependency, enum (+4 more)

### Community 118 - "entries"
Cohesion: 0.17
Nodes (12): additionalProperties, properties, type, grid, additionalProperties, properties, type, enum (+4 more)

### Community 119 - "required"
Cohesion: 0.33
Nodes (6): required, from, id, label, to, type

### Community 120 - "properties"
Cohesion: 0.17
Nodes (12): type, $ref, const, minItems, type, properties, activations, cards (+4 more)

### Community 121 - "legendEntry"
Cohesion: 0.18
Nodes (11): legendEntry, maxLength, minLength, type, additionalProperties, minProperties, properties, type (+3 more)

### Community 122 - "required"
Cohesion: 0.22
Nodes (11): items, minItems, type, additionalProperties, required, type, id, label (+3 more)

### Community 123 - "semanticRelation"
Cohesion: 0.18
Nodes (11): semanticRelation, $ref, from, to, from, to, additionalProperties, properties (+3 more)

### Community 124 - "generate-validators.mjs"
Cohesion: 0.18
Nodes (10): ajv, diagramTypes, __dirname, output, portableOutputWrappers, RESERVED_TYPE_NAMES, root, schemaIds (+2 more)

### Community 125 - "$ref"
Cohesion: 0.20
Nodes (10): items, type, $ref, items, type, attributes, methods, via (+2 more)

### Community 126 - "answer"
Cohesion: 0.14
Nodes (14): additionalProperties, properties, required, type, answer, reasons, scope, summary (+6 more)

### Community 127 - "image"
Cohesion: 0.20
Nodes (10): required, image, additionalProperties, required, type, kind, path, y (+2 more)

### Community 128 - "entries"
Cohesion: 0.20
Nodes (10): additionalProperties, properties, type, additionalProperties, properties, type, $ref, entries (+2 more)

### Community 129 - "entries"
Cohesion: 0.20
Nodes (10): additionalProperties, properties, type, additionalProperties, properties, type, $ref, entries (+2 more)

### Community 130 - "items"
Cohesion: 0.20
Nodes (10): additionalProperties, required, type, id, name, start, spans, items (+2 more)

### Community 131 - "entries"
Cohesion: 0.20
Nodes (10): additionalProperties, properties, type, additionalProperties, properties, type, $ref, entries (+2 more)

### Community 132 - "translations"
Cohesion: 0.22
Nodes (9): maxLength, minLength, type, translations, pattern, additionalProperties, maxProperties, propertyNames (+1 more)

### Community 133 - "enum"
Cohesion: 0.28
Nodes (9): visualPreset, blueprint, classic, editorial, signal-flow, enum, classic, visual_preset (+1 more)

### Community 134 - "enum"
Cohesion: 0.22
Nodes (9): description, enum, illustrative, evidence, description, enum, evidence, measured (+1 more)

### Community 135 - "tree.schema.json"
Cohesion: 0.22
Nodes (8): additionalProperties, $id, meta, nodes, required, $schema, title, type

### Community 136 - "items"
Cohesion: 0.22
Nodes (9): additionalProperties, required, type, id, label, items, minItems, type (+1 more)

### Community 138 - "wraps"
Cohesion: 0.25
Nodes (8): $ref, via, wraps, items, type, items, minItems, type

### Community 139 - "enum"
Cohesion: 0.25
Nodes (8): enum, amber, cyan, emerald, orange, rose, slate, violet

### Community 140 - "required"
Cohesion: 0.25
Nodes (8): required, id, items, label, path, title, dot, focus

### Community 141 - "properties"
Cohesion: 0.25
Nodes (8): type, list, additionalProperties, properties, type, type, checklist, ordered

### Community 142 - "facts"
Cohesion: 0.25
Nodes (8): facts, maxItems, minItems, type, additionalProperties, properties, type, entries

### Community 143 - "layout"
Cohesion: 0.25
Nodes (8): additionalProperties, properties, type, layout, width, description, minimum, type

### Community 144 - "collectNonFiniteAttrs"
Cohesion: 0.25
Nodes (8): attrEntries(), collectNonFiniteAttrs(), decodeNumericReferences(), ELEMENT_NUMERIC_ATTRS, HTML_VOID_ELEMENTS, isNumericAttr(), NUMERIC_ATTRS, SVG_HTML_INTEGRATION_POINTS

### Community 145 - "parse.mjs"
Cohesion: 0.38
Nodes (4): parseExplainer(), rowLabel(), stable(), TYPES

### Community 146 - "enum"
Cohesion: 0.29
Nodes (7): error, return, role, enum, async, branch, main

### Community 147 - "inline.mjs"
Cohesion: 0.53
Nodes (4): escapeHtml(), inlineError(), parseInline(), renderInline()

### Community 148 - "meta"
Cohesion: 0.33
Nodes (6): output, title, additionalProperties, required, type, meta

### Community 149 - "size"
Cohesion: 0.33
Nodes (6): size, items, maxItems, minItems, prefixItems, type

### Community 150 - "viewBox"
Cohesion: 0.33
Nodes (6): viewBox, items, maxItems, minItems, prefixItems, type

### Community 151 - "col"
Cohesion: 0.33
Nodes (6): description, maximum, minimum, multipleOf, type, col

### Community 152 - "portableOutputPath"
Cohesion: 0.33
Nodes (6): portableOutputPath, allOf, description, minLength, pattern, type

### Community 153 - "enum"
Cohesion: 0.40
Nodes (6): qualityProfile, showcase, standard, enum, quality_profile, enum

### Community 154 - "enum"
Cohesion: 0.33
Nodes (6): side, bottom, left, right, top, enum

### Community 155 - "enum"
Cohesion: 0.40
Nodes (6): enum, fromCardinality, toCardinality, enum, many, one

### Community 156 - "mainPath"
Cohesion: 0.33
Nodes (6): $ref, description, items, minItems, type, mainPath

### Community 157 - "meta"
Cohesion: 0.33
Nodes (6): output, title, additionalProperties, required, type, meta

### Community 158 - "sequence.schema.json"
Cohesion: 0.33
Nodes (5): additionalProperties, $id, $schema, title, type

### Community 159 - "meta"
Cohesion: 0.33
Nodes (6): output, title, additionalProperties, required, type, meta

### Community 160 - "enum"
Cohesion: 0.33
Nodes (6): change, enum, kind, action, alert, recovery

### Community 161 - "meta"
Cohesion: 0.33
Nodes (6): evidence, title, additionalProperties, required, type, meta

### Community 162 - "enum"
Cohesion: 0.33
Nodes (6): error, status, enum, cancelled, incomplete, ok

### Community 163 - "meta"
Cohesion: 0.33
Nodes (6): evidence, title, additionalProperties, required, type, meta

### Community 164 - "enum"
Cohesion: 0.33
Nodes (6): unit, description, enum, ms, s, us

### Community 165 - "meta"
Cohesion: 0.33
Nodes (6): output, title, additionalProperties, required, type, meta

### Community 166 - "viewBox"
Cohesion: 0.33
Nodes (6): viewBox, items, maxItems, minItems, prefixItems, type

### Community 167 - "delivery-update.mjs"
Cohesion: 0.70
Nodes (4): childPath, normalize(), startDeliveryUpdateCheck(), unavailable()

### Community 168 - "svg-path-analysis.mjs"
Cohesion: 0.70
Nodes (4): analyzeSvgPath(), ARITY, failure(), tokenize()

### Community 169 - "layout"
Cohesion: 0.40
Nodes (5): mode, additionalProperties, required, type, layout

### Community 170 - "enum"
Cohesion: 0.40
Nodes (5): legendMode, auto, enum, all, hidden

### Community 171 - "focus"
Cohesion: 0.40
Nodes (5): items, minItems, type, $ref, focus

### Community 172 - "required"
Cohesion: 0.40
Nodes (5): meta, nodes, required, flows, stages

### Community 173 - "layout"
Cohesion: 0.40
Nodes (5): mode, additionalProperties, required, type, layout

### Community 174 - "meta"
Cohesion: 0.40
Nodes (5): title, additionalProperties, required, type, meta

### Community 175 - "enum"
Cohesion: 0.40
Nodes (5): enum, level, note, open-question, warning

### Community 176 - "required"
Cohesion: 0.40
Nodes (5): meta, required, mainPath, states, transitions

### Community 177 - "enum"
Cohesion: 0.40
Nodes (5): description, enum, column_fit, fixed, spread

### Community 178 - "render-examples.mjs"
Cohesion: 0.40
Nodes (4): __dirname, outputRoot, skillRoot, TARGETS

### Community 179 - "validate45"
Cohesion: 0.50
Nodes (4): validate45(), validate46(), validate48(), validate50()

### Community 180 - "enum"
Cohesion: 0.50
Nodes (4): enum, kind, region, security-group

### Community 181 - "row"
Cohesion: 0.50
Nodes (4): row, maximum, minimum, type

### Community 182 - "via"
Cohesion: 0.50
Nodes (4): $ref, via, items, type

### Community 183 - "stages"
Cohesion: 0.50
Nodes (4): stages, maxItems, minItems, type

### Community 184 - "width"
Cohesion: 0.50
Nodes (4): width, minimum, $ref, type

### Community 185 - "col"
Cohesion: 0.50
Nodes (4): maximum, minimum, type, col

### Community 186 - "via"
Cohesion: 0.50
Nodes (4): $ref, via, items, type

### Community 187 - "viewBox"
Cohesion: 0.33
Nodes (6): viewBox, items, maxItems, minItems, prefixItems, type

### Community 188 - "width"
Cohesion: 0.50
Nodes (4): width, minimum, $ref, type

### Community 189 - "timezone"
Cohesion: 0.50
Nodes (4): timezone, description, minLength, type

### Community 190 - "enum"
Cohesion: 0.50
Nodes (4): enum, none, trace, animation

### Community 191 - "bias"
Cohesion: 0.50
Nodes (4): maximum, minimum, type, bias

### Community 192 - "fromCol"
Cohesion: 0.50
Nodes (4): maximum, minimum, type, fromCol

### Community 193 - "validate20"
Cohesion: 0.67
Nodes (3): validate20(), validate22(), validate24()

### Community 194 - "col"
Cohesion: 0.67
Nodes (3): minimum, type, col

### Community 195 - "height"
Cohesion: 0.67
Nodes (3): minimum, type, height

### Community 196 - "label"
Cohesion: 0.67
Nodes (3): minLength, type, label

### Community 197 - "at"
Cohesion: 0.50
Nodes (4): description, pattern, type, at

### Community 198 - "row"
Cohesion: 0.67
Nodes (3): row, minimum, type

### Community 199 - "stage"
Cohesion: 0.67
Nodes (3): stage, minimum, type

### Community 200 - "labelSegment"
Cohesion: 0.67
Nodes (3): minimum, type, labelSegment

### Community 201 - "label"
Cohesion: 0.67
Nodes (3): minLength, type, label

### Community 202 - "title"
Cohesion: 0.67
Nodes (3): title, minLength, type

### Community 203 - "to"
Cohesion: 0.67
Nodes (3): to, $ref, type

### Community 204 - "duration"
Cohesion: 0.67
Nodes (3): minimum, type, duration

### Community 205 - "height"
Cohesion: 0.67
Nodes (3): minimum, type, height

### Community 206 - "toCol"
Cohesion: 0.50
Nodes (4): toCol, maximum, minimum, type

### Community 207 - "width"
Cohesion: 0.67
Nodes (3): width, minimum, type

### Community 217 - "label"
Cohesion: 0.67
Nodes (3): minLength, type, label

### Community 218 - "labelSegment"
Cohesion: 0.67
Nodes (3): minimum, type, labelSegment

## Knowledge Gaps
- **1557 isolated node(s):** `__dirname`, `skillRoot`, `TYPES`, `DELIVERY_SIDECAR_SUFFIXES`, `COMPARE_SIDECAR_SUFFIXES` (+1552 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `image` connect `image` to `reader.js`, `$defs`, `id`?**
  _High betweenness centrality (0.365) - this node is a cross-community bridge._
- **Why does `pageImage()` connect `reader.js` to `image`?**
  _High betweenness centrality (0.356) - this node is a cross-community bridge._
- **Why does `diagramType` connect `diagramType` to `required`, `enum`, `required`, `tree.schema.json`?**
  _High betweenness centrality (0.335) - this node is a cross-community bridge._
- **What connects `__dirname`, `skillRoot`, `TYPES` to the rest of the system?**
  _1557 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `archify.mjs` be split into smaller, more focused modules?**
  _Cohesion score 0.0581267217630854 - nodes in this community are weakly interconnected._
- **Should `check-update.mjs` be split into smaller, more focused modules?**
  _Cohesion score 0.05427286356821589 - nodes in this community are weakly interconnected._
- **Should `render-erd.mjs` be split into smaller, more focused modules?**
  _Cohesion score 0.03766042499474016 - nodes in this community are weakly interconnected._