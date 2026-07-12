// @ts-nocheck -- generated Ajv standalone code is intentionally emitted as JavaScript.
/* eslint-disable */
/**
 * GENERATED from schema/cadgraph.schema.json.
 * Schema SHA-256: e56825a8ec3c4a3afdda9110560ce449d3e9fbf19dc2d5732b94b58696a65bec
 */
import type { ErrorObject } from "ajv";
import equalModule from "ajv/dist/runtime/equal.js";
import ucs2lengthModule from "ajv/dist/runtime/ucs2length.js";
import { fullFormats } from "ajv-formats/dist/formats.js";

export const CADGRAPH_SCHEMA_VERSION = "1.0.0" as const;
export const CADGRAPH_SCHEMA_SHA256 = "e56825a8ec3c4a3afdda9110560ce449d3e9fbf19dc2d5732b94b58696a65bec" as const;

const equal = typeof equalModule === "function" ? equalModule : equalModule.default;
const ucs2length = typeof ucs2lengthModule === "function" ? ucs2lengthModule : ucs2lengthModule.default;

export const validate = validate20;
export default validate20;
const schema31 = {"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://mesh2param.dev/schemas/cadgraph/1.0.0","title":"CADGraph","description":"Authoritative, editable and versioned Mesh2Param feature graph.","type":"object","additionalProperties":false,"required":["schemaVersion","id","name","units","sourceCoordinateFrame","projectTolerance","sketches","features","semanticTopology","sourceEvidence","userLocks","overrides","reconstructionSettings","engineVersions","deterministicSeed","fitMetrics","validation","versionMetadata"],"properties":{"schemaVersion":{"const":"1.0.0"},"id":{"$ref":"#/$defs/identifier"},"name":{"type":"string","minLength":1,"maxLength":200},"units":{"$ref":"#/$defs/units"},"source":{"anyOf":[{"$ref":"#/$defs/sourceAsset"},{"type":"null"}]},"sourceCoordinateFrame":{"$ref":"#/$defs/sourceCoordinateFrame"},"projectTolerance":{"$ref":"#/$defs/projectTolerance"},"sketches":{"type":"array","items":{"$ref":"#/$defs/sketch"}},"features":{"type":"array","items":{"$ref":"#/$defs/feature"}},"semanticTopology":{"type":"array","items":{"$ref":"#/$defs/semanticTopologyReference"}},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/sourceEvidence"}},"userLocks":{"type":"array","items":{"$ref":"#/$defs/userLock"}},"overrides":{"type":"array","items":{"$ref":"#/$defs/userOverride"}},"reconstructionSettings":{"$ref":"#/$defs/reconstructionSettings"},"engineVersions":{"$ref":"#/$defs/engineVersions"},"deterministicSeed":{"type":"integer","minimum":0,"maximum":4294967295},"fitMetrics":{"$ref":"#/$defs/fitMetrics"},"validation":{"$ref":"#/$defs/validationStatus"},"versionMetadata":{"$ref":"#/$defs/versionMetadata"},"extensions":{"type":["object","null"],"description":"Namespaced extension data. Core behavior must never depend on an unknown extension.","propertyNames":{"pattern":"^[a-z][a-z0-9.-]+/[A-Za-z0-9._-]+$"},"additionalProperties":{"$ref":"#/$defs/jsonValue"}}},"$defs":{"jsonValue":{"oneOf":[{"type":"null"},{"type":"boolean"},{"type":"number"},{"type":"string"},{"type":"array","items":{"$ref":"#/$defs/jsonValue"}},{"type":"object","additionalProperties":{"$ref":"#/$defs/jsonValue"}}]},"identifier":{"type":"string","minLength":1,"maxLength":160,"pattern":"^[A-Za-z][A-Za-z0-9._:-]*$"},"nullableIdentifier":{"anyOf":[{"$ref":"#/$defs/identifier"},{"type":"null"}]},"nullableTimestamp":{"type":["string","null"],"format":"date-time"},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"units":{"enum":["mm","cm","m","in","ft"]},"confidence":{"type":"number","minimum":0,"maximum":1},"vector2":{"type":"object","additionalProperties":false,"required":["x","y"],"properties":{"x":{"type":"number"},"y":{"type":"number"}}},"vector3":{"type":"object","additionalProperties":false,"required":["x","y","z"],"properties":{"x":{"type":"number"},"y":{"type":"number"},"z":{"type":"number"}}},"axis3":{"type":"object","additionalProperties":false,"required":["origin","direction"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"direction":{"$ref":"#/$defs/vector3"}}},"plane3":{"type":"object","additionalProperties":false,"required":["origin","normal","xAxis"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"normal":{"$ref":"#/$defs/vector3"},"xAxis":{"$ref":"#/$defs/vector3"}}},"sourceAsset":{"type":"object","additionalProperties":false,"required":["format","sha256","originalFileName","byteSize"],"properties":{"format":{"enum":["stl","obj","ply","cadgraph","generated"]},"sha256":{"$ref":"#/$defs/sha256"},"originalFileName":{"type":"string","minLength":1,"maxLength":255},"byteSize":{"type":"integer","minimum":0},"triangleCount":{"type":["integer","null"],"minimum":0},"declaredUnits":{"anyOf":[{"$ref":"#/$defs/units"},{"type":"null"}]},"scaleFactor":{"type":["number","null"],"exclusiveMinimum":0}}},"sourceCoordinateFrame":{"type":"object","additionalProperties":false,"required":["origin","xAxis","yAxis","zAxis","locked","confidence","evidenceIds"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"xAxis":{"$ref":"#/$defs/vector3"},"yAxis":{"$ref":"#/$defs/vector3"},"zAxis":{"$ref":"#/$defs/vector3"},"locked":{"type":"boolean"},"confidence":{"$ref":"#/$defs/confidence"},"evidenceIds":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true}}},"projectTolerance":{"type":"object","additionalProperties":false,"required":["surfaceDeviation","angularDeviationDeg","linearResolution"],"properties":{"surfaceDeviation":{"type":"number","exclusiveMinimum":0},"angularDeviationDeg":{"type":"number","exclusiveMinimum":0,"maximum":180},"linearResolution":{"type":"number","exclusiveMinimum":0}}},"sourceEvidence":{"type":"object","additionalProperties":false,"required":["id","sourceType","sourceIds","confidence"],"properties":{"id":{"$ref":"#/$defs/identifier"},"sourceType":{"enum":["meshPatch","meshTriangle","sketchEntity","feature","user","engine","imported","derived"]},"sourceIds":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"measuredValue":{"type":["number","null"]},"suggestedNominalValue":{"type":["number","null"]},"residual":{"type":["number","null"],"minimum":0},"confidence":{"$ref":"#/$defs/confidence"},"notes":{"type":["string","null"],"maxLength":2000},"metadata":{"type":["object","null"],"additionalProperties":{"$ref":"#/$defs/jsonValue"}}}},"userLock":{"type":"object","additionalProperties":false,"required":["target","locked","reason"],"properties":{"target":{"$ref":"#/$defs/identifier"},"locked":{"type":"boolean"},"reason":{"type":"string","maxLength":1000},"lockedAt":{"$ref":"#/$defs/nullableTimestamp"},"lockedBy":{"type":["string","null"],"maxLength":200}}},"userOverride":{"type":"object","additionalProperties":false,"required":["target","value","reason"],"properties":{"target":{"$ref":"#/$defs/identifier"},"value":{"$ref":"#/$defs/jsonValue"},"previousValue":{"$ref":"#/$defs/jsonValue"},"reason":{"type":"string","maxLength":1000},"createdAt":{"$ref":"#/$defs/nullableTimestamp"},"createdBy":{"type":["string","null"],"maxLength":200}}},"entityBase":{"type":"object","required":["id","kind","construction","sourceEvidence","confidence","locked","suppressed"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":["string","null"],"maxLength":200},"kind":{"type":"string"},"construction":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"},"suppressed":{"type":"boolean"}}},"pointEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["position"],"properties":{"kind":{"const":"point"},"construction":{"const":false},"position":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false},"constructionPointEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["position"],"properties":{"kind":{"const":"constructionPoint"},"construction":{"const":true},"position":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false},"lineEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["start","end"],"properties":{"kind":{"const":"line"},"construction":{"const":false},"start":{"$ref":"#/$defs/vector2"},"end":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false},"constructionLineEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["start","end"],"properties":{"kind":{"const":"constructionLine"},"construction":{"const":true},"start":{"$ref":"#/$defs/vector2"},"end":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false},"polylineEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["points","closed"],"properties":{"kind":{"const":"polyline"},"construction":{"const":false},"points":{"type":"array","minItems":2,"items":{"$ref":"#/$defs/vector2"}},"closed":{"type":"boolean"}}}],"unevaluatedProperties":false},"rectangleEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["origin","width","height","rotationDeg"],"properties":{"kind":{"const":"rectangle"},"construction":{"const":false},"origin":{"$ref":"#/$defs/vector2"},"width":{"type":"number","exclusiveMinimum":0},"height":{"type":"number","exclusiveMinimum":0},"rotationDeg":{"type":"number"}}}],"unevaluatedProperties":false},"circleEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["center","radius"],"properties":{"kind":{"const":"circle"},"construction":{"const":false},"center":{"$ref":"#/$defs/vector2"},"radius":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false},"circularArcEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["center","radius","startAngleDeg","endAngleDeg","clockwise"],"properties":{"kind":{"const":"circularArc"},"construction":{"const":false},"center":{"$ref":"#/$defs/vector2"},"radius":{"type":"number","exclusiveMinimum":0},"startAngleDeg":{"type":"number"},"endAngleDeg":{"type":"number"},"clockwise":{"type":"boolean"}}}],"unevaluatedProperties":false},"closedProfileEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["outerLoop","innerLoops","orientation"],"properties":{"kind":{"const":"closedProfile"},"construction":{"const":false},"outerLoop":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}},"innerLoops":{"type":"array","items":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}}},"orientation":{"enum":["clockwise","counterclockwise"]}}}],"unevaluatedProperties":false},"constructionAxisEntity":{"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["origin","direction"],"properties":{"kind":{"const":"constructionAxis"},"construction":{"const":true},"origin":{"$ref":"#/$defs/vector2"},"direction":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false},"sketchEntity":{"oneOf":[{"$ref":"#/$defs/pointEntity"},{"$ref":"#/$defs/constructionPointEntity"},{"$ref":"#/$defs/lineEntity"},{"$ref":"#/$defs/constructionLineEntity"},{"$ref":"#/$defs/polylineEntity"},{"$ref":"#/$defs/rectangleEntity"},{"$ref":"#/$defs/circleEntity"},{"$ref":"#/$defs/circularArcEntity"},{"$ref":"#/$defs/closedProfileEntity"},{"$ref":"#/$defs/constructionAxisEntity"}]},"sketchConstraint":{"type":"object","additionalProperties":false,"required":["id","kind","entityIds","driving","sourceEvidence","confidence","locked"],"properties":{"id":{"$ref":"#/$defs/identifier"},"kind":{"enum":["horizontal","vertical","coincident","parallel","perpendicular","equalLength","equalRadius","concentric","tangent","symmetric","fixed","distance","horizontalDistance","verticalDistance","angle","radius","diameter"]},"entityIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"value":{"type":["number","null"]},"measuredValue":{"type":["number","null"]},"suggestedNominalValue":{"type":["number","null"]},"nominalAccepted":{"type":["boolean","null"]},"unit":{"enum":["length","angle","none",null]},"driving":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"}}},"sketchProfile":{"type":"object","additionalProperties":false,"required":["id","outerLoop","innerLoops","orientation","closed","sourceEvidence","confidence","locked"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":["string","null"],"maxLength":200},"outerLoop":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}},"innerLoops":{"type":"array","items":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}}},"orientation":{"enum":["clockwise","counterclockwise"]},"closed":{"const":true},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"}}},"sketch":{"type":"object","additionalProperties":false,"required":["id","name","plane","entities","constraints","profiles","sourceEvidence","confidence","userLocks","overrides","suppressed"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":"string","minLength":1,"maxLength":200},"plane":{"$ref":"#/$defs/plane3"},"entities":{"type":"array","items":{"$ref":"#/$defs/sketchEntity"}},"constraints":{"type":"array","items":{"$ref":"#/$defs/sketchConstraint"}},"profiles":{"type":"array","items":{"$ref":"#/$defs/sketchProfile"}},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"userLocks":{"type":"array","items":{"$ref":"#/$defs/userLock"}},"overrides":{"type":"array","items":{"$ref":"#/$defs/userOverride"}},"suppressed":{"type":"boolean"}}},"featureBase":{"type":"object","required":["id","name","operation","order","dependencies","suppressed","sourceEvidence","confidence","userLocks","overrides","semanticOutputs"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":"string","minLength":1,"maxLength":200},"operation":{"type":"string"},"order":{"type":"integer","minimum":0},"dependencies":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"suppressed":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"userLocks":{"type":"array","items":{"$ref":"#/$defs/userLock"}},"overrides":{"type":"array","items":{"$ref":"#/$defs/userOverride"}},"semanticOutputs":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true}}},"extrusionFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","direction","extent"],"properties":{"operation":{"const":"extrusion"},"booleanMode":{"enum":["base","additive","subtractive"]},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"extent":{"enum":["blind","symmetric","throughAll","toFace"]},"distance":{"type":["number","null"],"exclusiveMinimum":0},"targetFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false},"pocketFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","direction","extent","depth"],"properties":{"operation":{"const":"pocket"},"booleanMode":{"const":"subtractive"},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"extent":{"enum":["blind","throughAll","toFace"]},"depth":{"type":"number","exclusiveMinimum":0},"targetFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false},"holeFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter"],"properties":{"operation":{"const":"hole"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"terminationFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false},"counterboreFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter","boreDiameter","boreDepth"],"properties":{"operation":{"const":"counterbore"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"boreDiameter":{"type":"number","exclusiveMinimum":0},"boreDepth":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false},"countersinkFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter","sinkDiameter","sinkAngleDeg"],"properties":{"operation":{"const":"countersink"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"sinkDiameter":{"type":"number","exclusiveMinimum":0},"sinkAngleDeg":{"type":"number","exclusiveMinimum":0,"maximum":179.999}}}],"unevaluatedProperties":false},"revolutionFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","axis","angleDeg"],"properties":{"operation":{"const":"revolution"},"booleanMode":{"enum":["base","additive","subtractive"]},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"axis":{"$ref":"#/$defs/axis3"},"angleDeg":{"type":"number","exclusiveMinimum":0,"maximum":360}}}],"unevaluatedProperties":false},"linearPatternFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","direction","count","spacing"],"properties":{"operation":{"const":"linearPattern"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"count":{"type":"integer","minimum":2},"spacing":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false},"circularPatternFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","axis","count","totalAngleDeg"],"properties":{"operation":{"const":"circularPattern"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"axis":{"$ref":"#/$defs/axis3"},"count":{"type":"integer","minimum":2},"totalAngleDeg":{"type":"number","exclusiveMinimum":0,"maximum":360}}}],"unevaluatedProperties":false},"mirrorFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","plane","keepOriginals"],"properties":{"operation":{"const":"mirror"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"plane":{"$ref":"#/$defs/plane3"},"keepOriginals":{"type":"boolean"}}}],"unevaluatedProperties":false},"chamferFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["targetEdges","width"],"properties":{"operation":{"const":"chamfer"},"targetEdges":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"width":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false},"filletFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["targetEdges","radius"],"properties":{"operation":{"const":"fillet"},"targetEdges":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"radius":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false},"importedFacetedFeature":{"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sourceArtifactId","meshSha256","intent"],"properties":{"operation":{"const":"importedFaceted"},"booleanMode":{"enum":["base","additive","subtractive"]},"sourceArtifactId":{"$ref":"#/$defs/identifier"},"meshSha256":{"$ref":"#/$defs/sha256"},"intent":{"enum":["fallback","reference"]},"sewingTolerance":{"type":"number","exclusiveMinimum":0,"maximum":10,"description":"Explicit OCCT sewing tolerance in project units. The engine additionally enforces a physical maximum equivalent to 10 mm. Omit to require an already-watertight mesh."}}}],"unevaluatedProperties":false},"feature":{"oneOf":[{"$ref":"#/$defs/extrusionFeature"},{"$ref":"#/$defs/pocketFeature"},{"$ref":"#/$defs/holeFeature"},{"$ref":"#/$defs/counterboreFeature"},{"$ref":"#/$defs/countersinkFeature"},{"$ref":"#/$defs/revolutionFeature"},{"$ref":"#/$defs/linearPatternFeature"},{"$ref":"#/$defs/circularPatternFeature"},{"$ref":"#/$defs/mirrorFeature"},{"$ref":"#/$defs/chamferFeature"},{"$ref":"#/$defs/filletFeature"},{"$ref":"#/$defs/importedFacetedFeature"}]},"semanticTopologyReference":{"type":"object","additionalProperties":false,"required":["id","kind","producerFeatureId","role","generatedFrom","status"],"properties":{"id":{"$ref":"#/$defs/identifier"},"kind":{"enum":["solid","shell","face","wire","edge","vertex","axis","plane"]},"producerFeatureId":{"$ref":"#/$defs/identifier"},"role":{"type":"string","minLength":1,"maxLength":200},"generatedFrom":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"status":{"enum":["resolved","unresolved"]},"kernelReference":{"type":["string","null"],"description":"Ephemeral diagnostic only; never the semantic identity."},"lastResolvedAt":{"$ref":"#/$defs/nullableTimestamp"}}},"scoreWeights":{"type":"object","additionalProperties":false,"required":["rmsDistance","p95Distance","maxDistance","normalAgreement","volumeDifference","overlap","sharpEdgeAlignment","boundaryAlignment","unmatchedSource","excessResult","complexity","unsupportedOperation","evidenceConfidence"],"properties":{"rmsDistance":{"type":"number","minimum":0},"p95Distance":{"type":"number","minimum":0},"maxDistance":{"type":"number","minimum":0},"normalAgreement":{"type":"number","minimum":0},"volumeDifference":{"type":"number","minimum":0},"overlap":{"type":"number","minimum":0},"sharpEdgeAlignment":{"type":"number","minimum":0},"boundaryAlignment":{"type":"number","minimum":0},"unmatchedSource":{"type":"number","minimum":0},"excessResult":{"type":"number","minimum":0},"complexity":{"type":"number","minimum":0},"unsupportedOperation":{"type":"number","minimum":0},"evidenceConfidence":{"type":"number","minimum":0}}},"reconstructionSettings":{"type":"object","additionalProperties":false,"required":["maxFeatures","beamWidth","candidatesPerResidual","wallClockSeconds","maxRebuilds","minScoreImprovement","nominalSnappingEnabled","nominalSnapTolerance","scoreWeights"],"properties":{"maxFeatures":{"type":"integer","minimum":1},"beamWidth":{"type":"integer","minimum":1},"candidatesPerResidual":{"type":"integer","minimum":1},"wallClockSeconds":{"type":"number","exclusiveMinimum":0},"maxRebuilds":{"type":"integer","minimum":1},"minScoreImprovement":{"type":"number","minimum":0},"nominalSnappingEnabled":{"type":"boolean"},"nominalSnapTolerance":{"type":"number","minimum":0},"scoreWeights":{"$ref":"#/$defs/scoreWeights"}}},"engineVersions":{"type":"object","additionalProperties":false,"required":["mesh2param","contracts","cadBackend","cadQuery","ocp","dependencies"],"properties":{"mesh2param":{"type":"string","minLength":1},"contracts":{"type":"string","minLength":1},"cadBackend":{"const":"OCCT"},"cadQuery":{"type":"string","minLength":1},"ocp":{"type":"string","minLength":1},"dependencies":{"type":"object","additionalProperties":{"type":"string"}}}},"fitMetrics":{"type":"object","additionalProperties":false,"required":["rmsSurfaceDistance","p95SurfaceDistance","maxSurfaceDistance","normalAgreement","volumeDifference","overlap","unmatchedSourceArea","excessResultArea","score"],"properties":{"rmsSurfaceDistance":{"type":"number","minimum":0},"p95SurfaceDistance":{"type":"number","minimum":0},"maxSurfaceDistance":{"type":"number","minimum":0},"normalAgreement":{"type":"number","minimum":0,"maximum":1},"volumeDifference":{"type":"number","minimum":0},"overlap":{"type":"number","minimum":0,"maximum":1},"unmatchedSourceArea":{"type":"number","minimum":0},"excessResultArea":{"type":"number","minimum":0},"score":{"type":"number"}}},"validationIssue":{"type":"object","additionalProperties":false,"required":["code","message","severity"],"properties":{"code":{"type":"string","minLength":1},"message":{"type":"string","minLength":1},"severity":{"enum":["info","warning","error"]},"featureId":{"$ref":"#/$defs/nullableIdentifier"},"semanticReference":{"$ref":"#/$defs/nullableIdentifier"},"details":{"type":["object","null"],"additionalProperties":{"$ref":"#/$defs/jsonValue"}}}},"validationStatus":{"type":"object","additionalProperties":false,"required":["status","brepValid","stepReimportValid","toleranceSatisfied","issues"],"properties":{"status":{"enum":["notRun","pending","valid","invalid","partial"]},"brepValid":{"type":["boolean","null"]},"stepReimportValid":{"type":["boolean","null"]},"toleranceSatisfied":{"type":["boolean","null"]},"checkedAt":{"$ref":"#/$defs/nullableTimestamp"},"lastValidFeatureId":{"$ref":"#/$defs/nullableIdentifier"},"issues":{"type":"array","items":{"$ref":"#/$defs/validationIssue"}}}},"versionMetadata":{"type":"object","additionalProperties":false,"required":["versionId","createdAt","createdBy","message"],"properties":{"versionId":{"$ref":"#/$defs/identifier"},"parentVersionId":{"$ref":"#/$defs/nullableIdentifier"},"createdAt":{"type":"string","format":"date-time"},"createdBy":{"type":"string","minLength":1,"maxLength":200},"message":{"type":"string","maxLength":1000}}}}};
const schema32 = {"type":"string","minLength":1,"maxLength":160,"pattern":"^[A-Za-z][A-Za-z0-9._:-]*$"};
const schema33 = {"enum":["mm","cm","m","in","ft"]};
const schema44 = {"type":"object","additionalProperties":false,"required":["surfaceDeviation","angularDeviationDeg","linearResolution"],"properties":{"surfaceDeviation":{"type":"number","exclusiveMinimum":0},"angularDeviationDeg":{"type":"number","exclusiveMinimum":0,"maximum":180},"linearResolution":{"type":"number","exclusiveMinimum":0}}};
const schema157 = {"type":"object","additionalProperties":false,"required":["mesh2param","contracts","cadBackend","cadQuery","ocp","dependencies"],"properties":{"mesh2param":{"type":"string","minLength":1},"contracts":{"type":"string","minLength":1},"cadBackend":{"const":"OCCT"},"cadQuery":{"type":"string","minLength":1},"ocp":{"type":"string","minLength":1},"dependencies":{"type":"object","additionalProperties":{"type":"string"}}}};
const schema158 = {"type":"object","additionalProperties":false,"required":["rmsSurfaceDistance","p95SurfaceDistance","maxSurfaceDistance","normalAgreement","volumeDifference","overlap","unmatchedSourceArea","excessResultArea","score"],"properties":{"rmsSurfaceDistance":{"type":"number","minimum":0},"p95SurfaceDistance":{"type":"number","minimum":0},"maxSurfaceDistance":{"type":"number","minimum":0},"normalAgreement":{"type":"number","minimum":0,"maximum":1},"volumeDifference":{"type":"number","minimum":0},"overlap":{"type":"number","minimum":0,"maximum":1},"unmatchedSourceArea":{"type":"number","minimum":0},"excessResultArea":{"type":"number","minimum":0},"score":{"type":"number"}}};
const func1 = Object.prototype.hasOwnProperty;
const func2 = ucs2length;
const pattern4 = new RegExp("^[A-Za-z][A-Za-z0-9._:-]*$", "u");
const pattern46 = new RegExp("^[a-z][a-z0-9.-]+/[A-Za-z0-9._-]+$", "u");
const schema34 = {"type":"object","additionalProperties":false,"required":["format","sha256","originalFileName","byteSize"],"properties":{"format":{"enum":["stl","obj","ply","cadgraph","generated"]},"sha256":{"$ref":"#/$defs/sha256"},"originalFileName":{"type":"string","minLength":1,"maxLength":255},"byteSize":{"type":"integer","minimum":0},"triangleCount":{"type":["integer","null"],"minimum":0},"declaredUnits":{"anyOf":[{"$ref":"#/$defs/units"},{"type":"null"}]},"scaleFactor":{"type":["number","null"],"exclusiveMinimum":0}}};
const schema35 = {"type":"string","pattern":"^[a-f0-9]{64}$"};
const pattern5 = new RegExp("^[a-f0-9]{64}$", "u");

function validate21(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate21.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.format === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "format"},message:"must have required property '"+"format"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sha256 === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sha256"},message:"must have required property '"+"sha256"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.originalFileName === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "originalFileName"},message:"must have required property '"+"originalFileName"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.byteSize === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "byteSize"},message:"must have required property '"+"byteSize"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
for(const key0 in data){
if(!(((((((key0 === "format") || (key0 === "sha256")) || (key0 === "originalFileName")) || (key0 === "byteSize")) || (key0 === "triangleCount")) || (key0 === "declaredUnits")) || (key0 === "scaleFactor"))){
const err4 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.format !== undefined){
let data0 = data.format;
if(!(((((data0 === "stl") || (data0 === "obj")) || (data0 === "ply")) || (data0 === "cadgraph")) || (data0 === "generated"))){
const err5 = {instancePath:instancePath+"/format",schemaPath:"#/properties/format/enum",keyword:"enum",params:{allowedValues: schema34.properties.format.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.sha256 !== undefined){
let data1 = data.sha256;
if(typeof data1 === "string"){
if(!pattern5.test(data1)){
const err6 = {instancePath:instancePath+"/sha256",schemaPath:"#/$defs/sha256/pattern",keyword:"pattern",params:{pattern: "^[a-f0-9]{64}$"},message:"must match pattern \""+"^[a-f0-9]{64}$"+"\""};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/sha256",schemaPath:"#/$defs/sha256/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.originalFileName !== undefined){
let data2 = data.originalFileName;
if(typeof data2 === "string"){
if(func2(data2) > 255){
const err8 = {instancePath:instancePath+"/originalFileName",schemaPath:"#/properties/originalFileName/maxLength",keyword:"maxLength",params:{limit: 255},message:"must NOT have more than 255 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(func2(data2) < 1){
const err9 = {instancePath:instancePath+"/originalFileName",schemaPath:"#/properties/originalFileName/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/originalFileName",schemaPath:"#/properties/originalFileName/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.byteSize !== undefined){
let data3 = data.byteSize;
if(!(((typeof data3 == "number") && (!(data3 % 1) && !isNaN(data3))) && (isFinite(data3)))){
const err11 = {instancePath:instancePath+"/byteSize",schemaPath:"#/properties/byteSize/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if((typeof data3 == "number") && (isFinite(data3))){
if(data3 < 0 || isNaN(data3)){
const err12 = {instancePath:instancePath+"/byteSize",schemaPath:"#/properties/byteSize/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
if(data.triangleCount !== undefined){
let data4 = data.triangleCount;
if((!(((typeof data4 == "number") && (!(data4 % 1) && !isNaN(data4))) && (isFinite(data4)))) && (data4 !== null)){
const err13 = {instancePath:instancePath+"/triangleCount",schemaPath:"#/properties/triangleCount/type",keyword:"type",params:{type: schema34.properties.triangleCount.type},message:"must be integer,null"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if((typeof data4 == "number") && (isFinite(data4))){
if(data4 < 0 || isNaN(data4)){
const err14 = {instancePath:instancePath+"/triangleCount",schemaPath:"#/properties/triangleCount/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
if(data.declaredUnits !== undefined){
let data5 = data.declaredUnits;
const _errs13 = errors;
let valid2 = false;
const _errs14 = errors;
if(!(((((data5 === "mm") || (data5 === "cm")) || (data5 === "m")) || (data5 === "in")) || (data5 === "ft"))){
const err15 = {instancePath:instancePath+"/declaredUnits",schemaPath:"#/$defs/units/enum",keyword:"enum",params:{allowedValues: schema33.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
var _valid0 = _errs14 === errors;
valid2 = valid2 || _valid0;
const _errs16 = errors;
if(data5 !== null){
const err16 = {instancePath:instancePath+"/declaredUnits",schemaPath:"#/properties/declaredUnits/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
var _valid0 = _errs16 === errors;
valid2 = valid2 || _valid0;
if(!valid2){
const err17 = {instancePath:instancePath+"/declaredUnits",schemaPath:"#/properties/declaredUnits/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
else {
errors = _errs13;
if(vErrors !== null){
if(_errs13){
vErrors.length = _errs13;
}
else {
vErrors = null;
}
}
}
}
if(data.scaleFactor !== undefined){
let data6 = data.scaleFactor;
if((!((typeof data6 == "number") && (isFinite(data6)))) && (data6 !== null)){
const err18 = {instancePath:instancePath+"/scaleFactor",schemaPath:"#/properties/scaleFactor/type",keyword:"type",params:{type: schema34.properties.scaleFactor.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if((typeof data6 == "number") && (isFinite(data6))){
if(data6 <= 0 || isNaN(data6)){
const err19 = {instancePath:instancePath+"/scaleFactor",schemaPath:"#/properties/scaleFactor/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
}
else {
const err20 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
validate21.errors = vErrors;
return errors === 0;
}
validate21.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema37 = {"type":"object","additionalProperties":false,"required":["origin","xAxis","yAxis","zAxis","locked","confidence","evidenceIds"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"xAxis":{"$ref":"#/$defs/vector3"},"yAxis":{"$ref":"#/$defs/vector3"},"zAxis":{"$ref":"#/$defs/vector3"},"locked":{"type":"boolean"},"confidence":{"$ref":"#/$defs/confidence"},"evidenceIds":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true}}};
const schema38 = {"type":"object","additionalProperties":false,"required":["x","y","z"],"properties":{"x":{"type":"number"},"y":{"type":"number"},"z":{"type":"number"}}};
const schema42 = {"type":"number","minimum":0,"maximum":1};
const func0 = equal;

function validate23(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate23.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.origin === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "origin"},message:"must have required property '"+"origin"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.xAxis === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "xAxis"},message:"must have required property '"+"xAxis"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.yAxis === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "yAxis"},message:"must have required property '"+"yAxis"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.zAxis === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "zAxis"},message:"must have required property '"+"zAxis"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.locked === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "locked"},message:"must have required property '"+"locked"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.confidence === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.evidenceIds === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "evidenceIds"},message:"must have required property '"+"evidenceIds"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
for(const key0 in data){
if(!(((((((key0 === "origin") || (key0 === "xAxis")) || (key0 === "yAxis")) || (key0 === "zAxis")) || (key0 === "locked")) || (key0 === "confidence")) || (key0 === "evidenceIds"))){
const err7 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.origin !== undefined){
let data0 = data.origin;
if(data0 && typeof data0 == "object" && !Array.isArray(data0)){
if(data0.x === undefined){
const err8 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data0.y === undefined){
const err9 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data0.z === undefined){
const err10 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
for(const key1 in data0){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err11 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data0.x !== undefined){
let data1 = data0.x;
if(!((typeof data1 == "number") && (isFinite(data1)))){
const err12 = {instancePath:instancePath+"/origin/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data0.y !== undefined){
let data2 = data0.y;
if(!((typeof data2 == "number") && (isFinite(data2)))){
const err13 = {instancePath:instancePath+"/origin/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data0.z !== undefined){
let data3 = data0.z;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err14 = {instancePath:instancePath+"/origin/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
else {
const err15 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.xAxis !== undefined){
let data4 = data.xAxis;
if(data4 && typeof data4 == "object" && !Array.isArray(data4)){
if(data4.x === undefined){
const err16 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data4.y === undefined){
const err17 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(data4.z === undefined){
const err18 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
for(const key2 in data4){
if(!(((key2 === "x") || (key2 === "y")) || (key2 === "z"))){
const err19 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data4.x !== undefined){
let data5 = data4.x;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err20 = {instancePath:instancePath+"/xAxis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data4.y !== undefined){
let data6 = data4.y;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err21 = {instancePath:instancePath+"/xAxis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data4.z !== undefined){
let data7 = data4.z;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err22 = {instancePath:instancePath+"/xAxis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
}
else {
const err23 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.yAxis !== undefined){
let data8 = data.yAxis;
if(data8 && typeof data8 == "object" && !Array.isArray(data8)){
if(data8.x === undefined){
const err24 = {instancePath:instancePath+"/yAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(data8.y === undefined){
const err25 = {instancePath:instancePath+"/yAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
if(data8.z === undefined){
const err26 = {instancePath:instancePath+"/yAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
for(const key3 in data8){
if(!(((key3 === "x") || (key3 === "y")) || (key3 === "z"))){
const err27 = {instancePath:instancePath+"/yAxis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key3},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data8.x !== undefined){
let data9 = data8.x;
if(!((typeof data9 == "number") && (isFinite(data9)))){
const err28 = {instancePath:instancePath+"/yAxis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
if(data8.y !== undefined){
let data10 = data8.y;
if(!((typeof data10 == "number") && (isFinite(data10)))){
const err29 = {instancePath:instancePath+"/yAxis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
if(data8.z !== undefined){
let data11 = data8.z;
if(!((typeof data11 == "number") && (isFinite(data11)))){
const err30 = {instancePath:instancePath+"/yAxis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
}
else {
const err31 = {instancePath:instancePath+"/yAxis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data.zAxis !== undefined){
let data12 = data.zAxis;
if(data12 && typeof data12 == "object" && !Array.isArray(data12)){
if(data12.x === undefined){
const err32 = {instancePath:instancePath+"/zAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(data12.y === undefined){
const err33 = {instancePath:instancePath+"/zAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
if(data12.z === undefined){
const err34 = {instancePath:instancePath+"/zAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
for(const key4 in data12){
if(!(((key4 === "x") || (key4 === "y")) || (key4 === "z"))){
const err35 = {instancePath:instancePath+"/zAxis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key4},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
if(data12.x !== undefined){
let data13 = data12.x;
if(!((typeof data13 == "number") && (isFinite(data13)))){
const err36 = {instancePath:instancePath+"/zAxis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
}
if(data12.y !== undefined){
let data14 = data12.y;
if(!((typeof data14 == "number") && (isFinite(data14)))){
const err37 = {instancePath:instancePath+"/zAxis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
}
if(data12.z !== undefined){
let data15 = data12.z;
if(!((typeof data15 == "number") && (isFinite(data15)))){
const err38 = {instancePath:instancePath+"/zAxis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
}
else {
const err39 = {instancePath:instancePath+"/zAxis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
if(data.locked !== undefined){
if(typeof data.locked !== "boolean"){
const err40 = {instancePath:instancePath+"/locked",schemaPath:"#/properties/locked/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
if(data.confidence !== undefined){
let data17 = data.confidence;
if((typeof data17 == "number") && (isFinite(data17))){
if(data17 > 1 || isNaN(data17)){
const err41 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
if(data17 < 0 || isNaN(data17)){
const err42 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
}
else {
const err43 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
}
}
if(data.evidenceIds !== undefined){
let data18 = data.evidenceIds;
if(Array.isArray(data18)){
const len0 = data18.length;
for(let i0=0; i0<len0; i0++){
let data19 = data18[i0];
if(typeof data19 === "string"){
if(func2(data19) > 160){
const err44 = {instancePath:instancePath+"/evidenceIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
if(func2(data19) < 1){
const err45 = {instancePath:instancePath+"/evidenceIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
if(!pattern4.test(data19)){
const err46 = {instancePath:instancePath+"/evidenceIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err46];
}
else {
vErrors.push(err46);
}
errors++;
}
}
else {
const err47 = {instancePath:instancePath+"/evidenceIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err47];
}
else {
vErrors.push(err47);
}
errors++;
}
}
let i1 = data18.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data18[i1], data18[j0])){
const err48 = {instancePath:instancePath+"/evidenceIds",schemaPath:"#/properties/evidenceIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err48];
}
else {
vErrors.push(err48);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err49 = {instancePath:instancePath+"/evidenceIds",schemaPath:"#/properties/evidenceIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err49];
}
else {
vErrors.push(err49);
}
errors++;
}
}
}
else {
const err50 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err50];
}
else {
vErrors.push(err50);
}
errors++;
}
validate23.errors = vErrors;
return errors === 0;
}
validate23.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema45 = {"type":"object","additionalProperties":false,"required":["id","name","plane","entities","constraints","profiles","sourceEvidence","confidence","userLocks","overrides","suppressed"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":"string","minLength":1,"maxLength":200},"plane":{"$ref":"#/$defs/plane3"},"entities":{"type":"array","items":{"$ref":"#/$defs/sketchEntity"}},"constraints":{"type":"array","items":{"$ref":"#/$defs/sketchConstraint"}},"profiles":{"type":"array","items":{"$ref":"#/$defs/sketchProfile"}},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"userLocks":{"type":"array","items":{"$ref":"#/$defs/userLock"}},"overrides":{"type":"array","items":{"$ref":"#/$defs/userOverride"}},"suppressed":{"type":"boolean"}}};
const schema47 = {"type":"object","additionalProperties":false,"required":["origin","normal","xAxis"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"normal":{"$ref":"#/$defs/vector3"},"xAxis":{"$ref":"#/$defs/vector3"}}};

function validate26(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate26.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.origin === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "origin"},message:"must have required property '"+"origin"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.normal === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "normal"},message:"must have required property '"+"normal"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.xAxis === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "xAxis"},message:"must have required property '"+"xAxis"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
for(const key0 in data){
if(!(((key0 === "origin") || (key0 === "normal")) || (key0 === "xAxis"))){
const err3 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.origin !== undefined){
let data0 = data.origin;
if(data0 && typeof data0 == "object" && !Array.isArray(data0)){
if(data0.x === undefined){
const err4 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data0.y === undefined){
const err5 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data0.z === undefined){
const err6 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
for(const key1 in data0){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err7 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data0.x !== undefined){
let data1 = data0.x;
if(!((typeof data1 == "number") && (isFinite(data1)))){
const err8 = {instancePath:instancePath+"/origin/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data0.y !== undefined){
let data2 = data0.y;
if(!((typeof data2 == "number") && (isFinite(data2)))){
const err9 = {instancePath:instancePath+"/origin/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data0.z !== undefined){
let data3 = data0.z;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err10 = {instancePath:instancePath+"/origin/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
else {
const err11 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.normal !== undefined){
let data4 = data.normal;
if(data4 && typeof data4 == "object" && !Array.isArray(data4)){
if(data4.x === undefined){
const err12 = {instancePath:instancePath+"/normal",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data4.y === undefined){
const err13 = {instancePath:instancePath+"/normal",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data4.z === undefined){
const err14 = {instancePath:instancePath+"/normal",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
for(const key2 in data4){
if(!(((key2 === "x") || (key2 === "y")) || (key2 === "z"))){
const err15 = {instancePath:instancePath+"/normal",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data4.x !== undefined){
let data5 = data4.x;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err16 = {instancePath:instancePath+"/normal/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data4.y !== undefined){
let data6 = data4.y;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err17 = {instancePath:instancePath+"/normal/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data4.z !== undefined){
let data7 = data4.z;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err18 = {instancePath:instancePath+"/normal/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
else {
const err19 = {instancePath:instancePath+"/normal",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data.xAxis !== undefined){
let data8 = data.xAxis;
if(data8 && typeof data8 == "object" && !Array.isArray(data8)){
if(data8.x === undefined){
const err20 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if(data8.y === undefined){
const err21 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(data8.z === undefined){
const err22 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
for(const key3 in data8){
if(!(((key3 === "x") || (key3 === "y")) || (key3 === "z"))){
const err23 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key3},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data8.x !== undefined){
let data9 = data8.x;
if(!((typeof data9 == "number") && (isFinite(data9)))){
const err24 = {instancePath:instancePath+"/xAxis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data8.y !== undefined){
let data10 = data8.y;
if(!((typeof data10 == "number") && (isFinite(data10)))){
const err25 = {instancePath:instancePath+"/xAxis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data8.z !== undefined){
let data11 = data8.z;
if(!((typeof data11 == "number") && (isFinite(data11)))){
const err26 = {instancePath:instancePath+"/xAxis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
}
else {
const err27 = {instancePath:instancePath+"/xAxis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
}
else {
const err28 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
validate26.errors = vErrors;
return errors === 0;
}
validate26.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema51 = {"oneOf":[{"$ref":"#/$defs/pointEntity"},{"$ref":"#/$defs/constructionPointEntity"},{"$ref":"#/$defs/lineEntity"},{"$ref":"#/$defs/constructionLineEntity"},{"$ref":"#/$defs/polylineEntity"},{"$ref":"#/$defs/rectangleEntity"},{"$ref":"#/$defs/circleEntity"},{"$ref":"#/$defs/circularArcEntity"},{"$ref":"#/$defs/closedProfileEntity"},{"$ref":"#/$defs/constructionAxisEntity"}]};
const schema52 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["position"],"properties":{"kind":{"const":"point"},"construction":{"const":false},"position":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false};
const schema57 = {"type":"object","additionalProperties":false,"required":["x","y"],"properties":{"x":{"type":"number"},"y":{"type":"number"}}};
const schema53 = {"type":"object","required":["id","kind","construction","sourceEvidence","confidence","locked","suppressed"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":["string","null"],"maxLength":200},"kind":{"type":"string"},"construction":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"},"suppressed":{"type":"boolean"}}};

function validate30(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate30.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.kind === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "kind"},message:"must have required property '"+"kind"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.construction === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "construction"},message:"must have required property '"+"construction"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.confidence === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.locked === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "locked"},message:"must have required property '"+"locked"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.suppressed === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "suppressed"},message:"must have required property '"+"suppressed"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err7 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(func2(data0) < 1){
const err8 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(!pattern4.test(data0)){
const err9 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.name !== undefined){
let data1 = data.name;
if((typeof data1 !== "string") && (data1 !== null)){
const err11 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/type",keyword:"type",params:{type: schema53.properties.name.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(typeof data1 === "string"){
if(func2(data1) > 200){
const err12 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
if(data.kind !== undefined){
if(typeof data.kind !== "string"){
const err13 = {instancePath:instancePath+"/kind",schemaPath:"#/properties/kind/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data.construction !== undefined){
if(typeof data.construction !== "boolean"){
const err14 = {instancePath:instancePath+"/construction",schemaPath:"#/properties/construction/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data4 = data.sourceEvidence;
if(Array.isArray(data4)){
const len0 = data4.length;
for(let i0=0; i0<len0; i0++){
let data5 = data4[i0];
if(typeof data5 === "string"){
if(func2(data5) > 160){
const err15 = {instancePath:instancePath+"/sourceEvidence/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
if(func2(data5) < 1){
const err16 = {instancePath:instancePath+"/sourceEvidence/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(!pattern4.test(data5)){
const err17 = {instancePath:instancePath+"/sourceEvidence/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
else {
const err18 = {instancePath:instancePath+"/sourceEvidence/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
let i1 = data4.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data4[i1], data4[j0])){
const err19 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err20 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.confidence !== undefined){
let data6 = data.confidence;
if((typeof data6 == "number") && (isFinite(data6))){
if(data6 > 1 || isNaN(data6)){
const err21 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(data6 < 0 || isNaN(data6)){
const err22 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
else {
const err23 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.locked !== undefined){
if(typeof data.locked !== "boolean"){
const err24 = {instancePath:instancePath+"/locked",schemaPath:"#/properties/locked/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data.suppressed !== undefined){
if(typeof data.suppressed !== "boolean"){
const err25 = {instancePath:instancePath+"/suppressed",schemaPath:"#/properties/suppressed/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
else {
const err26 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
validate30.errors = vErrors;
return errors === 0;
}
validate30.evaluated = {"props":{"id":true,"name":true,"kind":true,"construction":true,"sourceEvidence":true,"confidence":true,"locked":true,"suppressed":true},"dynamicProps":false,"dynamicItems":false};


function validate29(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate29.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.position === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "position"},message:"must have required property '"+"position"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.kind !== undefined){
if("point" !== data.kind){
const err1 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "point"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err2 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.position !== undefined){
let data2 = data.position;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err3 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data2.y === undefined){
const err4 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err5 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err6 = {instancePath:instancePath+"/position/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err7 = {instancePath:instancePath+"/position/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
}
else {
const err8 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if(((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "position")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err10 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
validate29.errors = vErrors;
return errors === 0;
}
validate29.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema58 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["position"],"properties":{"kind":{"const":"constructionPoint"},"construction":{"const":true},"position":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false};

function validate33(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate33.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.position === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "position"},message:"must have required property '"+"position"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.kind !== undefined){
if("constructionPoint" !== data.kind){
const err1 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "constructionPoint"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
}
if(data.construction !== undefined){
if(true !== data.construction){
const err2 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: true},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.position !== undefined){
let data2 = data.position;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err3 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data2.y === undefined){
const err4 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err5 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err6 = {instancePath:instancePath+"/position/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err7 = {instancePath:instancePath+"/position/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
}
else {
const err8 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if(((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "position")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err10 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
validate33.errors = vErrors;
return errors === 0;
}
validate33.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema60 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["start","end"],"properties":{"kind":{"const":"line"},"construction":{"const":false},"start":{"$ref":"#/$defs/vector2"},"end":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false};

function validate36(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate36.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.start === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.end === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.kind !== undefined){
if("line" !== data.kind){
const err2 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "line"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err3 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.start !== undefined){
let data2 = data.start;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err4 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data2.y === undefined){
const err5 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err6 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err7 = {instancePath:instancePath+"/start/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err8 = {instancePath:instancePath+"/start/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.end !== undefined){
let data5 = data.end;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.x === undefined){
const err10 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data5.y === undefined){
const err11 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
for(const key1 in data5){
if(!((key1 === "x") || (key1 === "y"))){
const err12 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data5.x !== undefined){
let data6 = data5.x;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err13 = {instancePath:instancePath+"/end/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data5.y !== undefined){
let data7 = data5.y;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err14 = {instancePath:instancePath+"/end/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
else {
const err15 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if((((((((((key2 !== "kind") && (key2 !== "construction")) && (key2 !== "start")) && (key2 !== "end")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "locked")) && (key2 !== "suppressed")){
const err17 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
validate36.errors = vErrors;
return errors === 0;
}
validate36.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema63 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["start","end"],"properties":{"kind":{"const":"constructionLine"},"construction":{"const":true},"start":{"$ref":"#/$defs/vector2"},"end":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false};

function validate39(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate39.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.start === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.end === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.kind !== undefined){
if("constructionLine" !== data.kind){
const err2 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "constructionLine"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.construction !== undefined){
if(true !== data.construction){
const err3 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: true},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.start !== undefined){
let data2 = data.start;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err4 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data2.y === undefined){
const err5 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err6 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err7 = {instancePath:instancePath+"/start/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err8 = {instancePath:instancePath+"/start/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath:instancePath+"/start",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.end !== undefined){
let data5 = data.end;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.x === undefined){
const err10 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data5.y === undefined){
const err11 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
for(const key1 in data5){
if(!((key1 === "x") || (key1 === "y"))){
const err12 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data5.x !== undefined){
let data6 = data5.x;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err13 = {instancePath:instancePath+"/end/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data5.y !== undefined){
let data7 = data5.y;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err14 = {instancePath:instancePath+"/end/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
else {
const err15 = {instancePath:instancePath+"/end",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if((((((((((key2 !== "kind") && (key2 !== "construction")) && (key2 !== "start")) && (key2 !== "end")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "locked")) && (key2 !== "suppressed")){
const err17 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
validate39.errors = vErrors;
return errors === 0;
}
validate39.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema66 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["points","closed"],"properties":{"kind":{"const":"polyline"},"construction":{"const":false},"points":{"type":"array","minItems":2,"items":{"$ref":"#/$defs/vector2"}},"closed":{"type":"boolean"}}}],"unevaluatedProperties":false};

function validate42(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate42.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.points === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "points"},message:"must have required property '"+"points"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.closed === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "closed"},message:"must have required property '"+"closed"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.kind !== undefined){
if("polyline" !== data.kind){
const err2 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "polyline"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err3 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.points !== undefined){
let data2 = data.points;
if(Array.isArray(data2)){
if(data2.length < 2){
const err4 = {instancePath:instancePath+"/points",schemaPath:"#/allOf/1/properties/points/minItems",keyword:"minItems",params:{limit: 2},message:"must NOT have fewer than 2 items"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
let data3 = data2[i0];
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
if(data3.x === undefined){
const err5 = {instancePath:instancePath+"/points/" + i0,schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data3.y === undefined){
const err6 = {instancePath:instancePath+"/points/" + i0,schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
for(const key0 in data3){
if(!((key0 === "x") || (key0 === "y"))){
const err7 = {instancePath:instancePath+"/points/" + i0,schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data3.x !== undefined){
let data4 = data3.x;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err8 = {instancePath:instancePath+"/points/" + i0+"/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data3.y !== undefined){
let data5 = data3.y;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err9 = {instancePath:instancePath+"/points/" + i0+"/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
}
else {
const err10 = {instancePath:instancePath+"/points/" + i0,schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
else {
const err11 = {instancePath:instancePath+"/points",schemaPath:"#/allOf/1/properties/points/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.closed !== undefined){
if(typeof data.closed !== "boolean"){
const err12 = {instancePath:instancePath+"/closed",schemaPath:"#/allOf/1/properties/closed/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
else {
const err13 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if((((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "points")) && (key1 !== "closed")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err14 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
validate42.errors = vErrors;
return errors === 0;
}
validate42.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema68 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["origin","width","height","rotationDeg"],"properties":{"kind":{"const":"rectangle"},"construction":{"const":false},"origin":{"$ref":"#/$defs/vector2"},"width":{"type":"number","exclusiveMinimum":0},"height":{"type":"number","exclusiveMinimum":0},"rotationDeg":{"type":"number"}}}],"unevaluatedProperties":false};

function validate45(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate45.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.origin === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "origin"},message:"must have required property '"+"origin"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.width === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.height === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.rotationDeg === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "rotationDeg"},message:"must have required property '"+"rotationDeg"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.kind !== undefined){
if("rectangle" !== data.kind){
const err4 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "rectangle"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err5 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.origin !== undefined){
let data2 = data.origin;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err6 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data2.y === undefined){
const err7 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err8 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err9 = {instancePath:instancePath+"/origin/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err10 = {instancePath:instancePath+"/origin/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
else {
const err11 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.width !== undefined){
let data5 = data.width;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 <= 0 || isNaN(data5)){
const err12 = {instancePath:instancePath+"/width",schemaPath:"#/allOf/1/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
else {
const err13 = {instancePath:instancePath+"/width",schemaPath:"#/allOf/1/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data.height !== undefined){
let data6 = data.height;
if((typeof data6 == "number") && (isFinite(data6))){
if(data6 <= 0 || isNaN(data6)){
const err14 = {instancePath:instancePath+"/height",schemaPath:"#/allOf/1/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/height",schemaPath:"#/allOf/1/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.rotationDeg !== undefined){
let data7 = data.rotationDeg;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err16 = {instancePath:instancePath+"/rotationDeg",schemaPath:"#/allOf/1/properties/rotationDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if((((((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "origin")) && (key1 !== "width")) && (key1 !== "height")) && (key1 !== "rotationDeg")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err18 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
validate45.errors = vErrors;
return errors === 0;
}
validate45.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema70 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["center","radius"],"properties":{"kind":{"const":"circle"},"construction":{"const":false},"center":{"$ref":"#/$defs/vector2"},"radius":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false};

function validate48(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate48.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.center === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "center"},message:"must have required property '"+"center"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.radius === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "radius"},message:"must have required property '"+"radius"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.kind !== undefined){
if("circle" !== data.kind){
const err2 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "circle"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err3 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.center !== undefined){
let data2 = data.center;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err4 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data2.y === undefined){
const err5 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err6 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err7 = {instancePath:instancePath+"/center/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err8 = {instancePath:instancePath+"/center/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.radius !== undefined){
let data5 = data.radius;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 <= 0 || isNaN(data5)){
const err10 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if((((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "center")) && (key1 !== "radius")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err13 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
validate48.errors = vErrors;
return errors === 0;
}
validate48.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema72 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["center","radius","startAngleDeg","endAngleDeg","clockwise"],"properties":{"kind":{"const":"circularArc"},"construction":{"const":false},"center":{"$ref":"#/$defs/vector2"},"radius":{"type":"number","exclusiveMinimum":0},"startAngleDeg":{"type":"number"},"endAngleDeg":{"type":"number"},"clockwise":{"type":"boolean"}}}],"unevaluatedProperties":false};

function validate51(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate51.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.center === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "center"},message:"must have required property '"+"center"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.radius === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "radius"},message:"must have required property '"+"radius"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.startAngleDeg === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "startAngleDeg"},message:"must have required property '"+"startAngleDeg"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.endAngleDeg === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "endAngleDeg"},message:"must have required property '"+"endAngleDeg"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.clockwise === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "clockwise"},message:"must have required property '"+"clockwise"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.kind !== undefined){
if("circularArc" !== data.kind){
const err5 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "circularArc"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err6 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.center !== undefined){
let data2 = data.center;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err7 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data2.y === undefined){
const err8 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err9 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err10 = {instancePath:instancePath+"/center/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err11 = {instancePath:instancePath+"/center/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath:instancePath+"/center",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data.radius !== undefined){
let data5 = data.radius;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 <= 0 || isNaN(data5)){
const err13 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
else {
const err14 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data.startAngleDeg !== undefined){
let data6 = data.startAngleDeg;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err15 = {instancePath:instancePath+"/startAngleDeg",schemaPath:"#/allOf/1/properties/startAngleDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.endAngleDeg !== undefined){
let data7 = data.endAngleDeg;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err16 = {instancePath:instancePath+"/endAngleDeg",schemaPath:"#/allOf/1/properties/endAngleDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data.clockwise !== undefined){
if(typeof data.clockwise !== "boolean"){
const err17 = {instancePath:instancePath+"/clockwise",schemaPath:"#/allOf/1/properties/clockwise/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
else {
const err18 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if(((((((((((((key1 !== "kind") && (key1 !== "construction")) && (key1 !== "center")) && (key1 !== "radius")) && (key1 !== "startAngleDeg")) && (key1 !== "endAngleDeg")) && (key1 !== "clockwise")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "locked")) && (key1 !== "suppressed")){
const err19 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
validate51.errors = vErrors;
return errors === 0;
}
validate51.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema74 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["outerLoop","innerLoops","orientation"],"properties":{"kind":{"const":"closedProfile"},"construction":{"const":false},"outerLoop":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}},"innerLoops":{"type":"array","items":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}}},"orientation":{"enum":["clockwise","counterclockwise"]}}}],"unevaluatedProperties":false};

function validate54(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate54.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.outerLoop === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "outerLoop"},message:"must have required property '"+"outerLoop"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.innerLoops === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "innerLoops"},message:"must have required property '"+"innerLoops"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.orientation === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "orientation"},message:"must have required property '"+"orientation"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.kind !== undefined){
if("closedProfile" !== data.kind){
const err3 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "closedProfile"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.construction !== undefined){
if(false !== data.construction){
const err4 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: false},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.outerLoop !== undefined){
let data2 = data.outerLoop;
if(Array.isArray(data2)){
if(data2.length < 1){
const err5 = {instancePath:instancePath+"/outerLoop",schemaPath:"#/allOf/1/properties/outerLoop/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
let data3 = data2[i0];
if(typeof data3 === "string"){
if(func2(data3) > 160){
const err6 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(func2(data3) < 1){
const err7 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(!pattern4.test(data3)){
const err8 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
else {
const err9 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
}
else {
const err10 = {instancePath:instancePath+"/outerLoop",schemaPath:"#/allOf/1/properties/outerLoop/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.innerLoops !== undefined){
let data4 = data.innerLoops;
if(Array.isArray(data4)){
const len1 = data4.length;
for(let i1=0; i1<len1; i1++){
let data5 = data4[i1];
if(Array.isArray(data5)){
if(data5.length < 1){
const err11 = {instancePath:instancePath+"/innerLoops/" + i1,schemaPath:"#/allOf/1/properties/innerLoops/items/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
const len2 = data5.length;
for(let i2=0; i2<len2; i2++){
let data6 = data5[i2];
if(typeof data6 === "string"){
if(func2(data6) > 160){
const err12 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(func2(data6) < 1){
const err13 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(!pattern4.test(data6)){
const err14 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath:instancePath+"/innerLoops/" + i1,schemaPath:"#/allOf/1/properties/innerLoops/items/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath:instancePath+"/innerLoops",schemaPath:"#/allOf/1/properties/innerLoops/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.orientation !== undefined){
let data7 = data.orientation;
if(!((data7 === "clockwise") || (data7 === "counterclockwise"))){
const err18 = {instancePath:instancePath+"/orientation",schemaPath:"#/allOf/1/properties/orientation/enum",keyword:"enum",params:{allowedValues: schema74.allOf[1].properties.orientation.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
else {
const err19 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if(((((((((((key0 !== "kind") && (key0 !== "construction")) && (key0 !== "outerLoop")) && (key0 !== "innerLoops")) && (key0 !== "orientation")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "locked")) && (key0 !== "suppressed")){
const err20 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
}
validate54.errors = vErrors;
return errors === 0;
}
validate54.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema77 = {"allOf":[{"$ref":"#/$defs/entityBase"},{"type":"object","required":["origin","direction"],"properties":{"kind":{"const":"constructionAxis"},"construction":{"const":true},"origin":{"$ref":"#/$defs/vector2"},"direction":{"$ref":"#/$defs/vector2"}}}],"unevaluatedProperties":false};

function validate57(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate57.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate30(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate30.errors : vErrors.concat(validate30.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.origin === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "origin"},message:"must have required property '"+"origin"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.direction === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.kind !== undefined){
if("constructionAxis" !== data.kind){
const err2 = {instancePath:instancePath+"/kind",schemaPath:"#/allOf/1/properties/kind/const",keyword:"const",params:{allowedValue: "constructionAxis"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.construction !== undefined){
if(true !== data.construction){
const err3 = {instancePath:instancePath+"/construction",schemaPath:"#/allOf/1/properties/construction/const",keyword:"const",params:{allowedValue: true},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.origin !== undefined){
let data2 = data.origin;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.x === undefined){
const err4 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data2.y === undefined){
const err5 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key0 in data2){
if(!((key0 === "x") || (key0 === "y"))){
const err6 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data2.x !== undefined){
let data3 = data2.x;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err7 = {instancePath:instancePath+"/origin/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data2.y !== undefined){
let data4 = data2.y;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err8 = {instancePath:instancePath+"/origin/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
else {
const err9 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.direction !== undefined){
let data5 = data.direction;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.x === undefined){
const err10 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data5.y === undefined){
const err11 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector2/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
for(const key1 in data5){
if(!((key1 === "x") || (key1 === "y"))){
const err12 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data5.x !== undefined){
let data6 = data5.x;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err13 = {instancePath:instancePath+"/direction/x",schemaPath:"#/$defs/vector2/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data5.y !== undefined){
let data7 = data5.y;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err14 = {instancePath:instancePath+"/direction/y",schemaPath:"#/$defs/vector2/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
else {
const err15 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if((((((((((key2 !== "kind") && (key2 !== "construction")) && (key2 !== "origin")) && (key2 !== "direction")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "locked")) && (key2 !== "suppressed")){
const err17 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
validate57.errors = vErrors;
return errors === 0;
}
validate57.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate28(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate28.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
const _errs0 = errors;
let valid0 = false;
let passing0 = null;
const _errs1 = errors;
if(!(validate29(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate29.errors : vErrors.concat(validate29.errors);
errors = vErrors.length;
}
var _valid0 = _errs1 === errors;
if(_valid0){
valid0 = true;
passing0 = 0;
var props0 = true;
}
const _errs2 = errors;
if(!(validate33(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate33.errors : vErrors.concat(validate33.errors);
errors = vErrors.length;
}
var _valid0 = _errs2 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 1];
}
else {
if(_valid0){
valid0 = true;
passing0 = 1;
if(props0 !== true){
props0 = true;
}
}
const _errs3 = errors;
if(!(validate36(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate36.errors : vErrors.concat(validate36.errors);
errors = vErrors.length;
}
var _valid0 = _errs3 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 2];
}
else {
if(_valid0){
valid0 = true;
passing0 = 2;
if(props0 !== true){
props0 = true;
}
}
const _errs4 = errors;
if(!(validate39(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate39.errors : vErrors.concat(validate39.errors);
errors = vErrors.length;
}
var _valid0 = _errs4 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 3];
}
else {
if(_valid0){
valid0 = true;
passing0 = 3;
if(props0 !== true){
props0 = true;
}
}
const _errs5 = errors;
if(!(validate42(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate42.errors : vErrors.concat(validate42.errors);
errors = vErrors.length;
}
var _valid0 = _errs5 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 4];
}
else {
if(_valid0){
valid0 = true;
passing0 = 4;
if(props0 !== true){
props0 = true;
}
}
const _errs6 = errors;
if(!(validate45(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate45.errors : vErrors.concat(validate45.errors);
errors = vErrors.length;
}
var _valid0 = _errs6 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 5];
}
else {
if(_valid0){
valid0 = true;
passing0 = 5;
if(props0 !== true){
props0 = true;
}
}
const _errs7 = errors;
if(!(validate48(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate48.errors : vErrors.concat(validate48.errors);
errors = vErrors.length;
}
var _valid0 = _errs7 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 6];
}
else {
if(_valid0){
valid0 = true;
passing0 = 6;
if(props0 !== true){
props0 = true;
}
}
const _errs8 = errors;
if(!(validate51(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate51.errors : vErrors.concat(validate51.errors);
errors = vErrors.length;
}
var _valid0 = _errs8 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 7];
}
else {
if(_valid0){
valid0 = true;
passing0 = 7;
if(props0 !== true){
props0 = true;
}
}
const _errs9 = errors;
if(!(validate54(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate54.errors : vErrors.concat(validate54.errors);
errors = vErrors.length;
}
var _valid0 = _errs9 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 8];
}
else {
if(_valid0){
valid0 = true;
passing0 = 8;
if(props0 !== true){
props0 = true;
}
}
const _errs10 = errors;
if(!(validate57(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate57.errors : vErrors.concat(validate57.errors);
errors = vErrors.length;
}
var _valid0 = _errs10 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 9];
}
else {
if(_valid0){
valid0 = true;
passing0 = 9;
if(props0 !== true){
props0 = true;
}
}
}
}
}
}
}
}
}
}
}
if(!valid0){
const err0 = {instancePath,schemaPath:"#/oneOf",keyword:"oneOf",params:{passingSchemas: passing0},message:"must match exactly one schema in oneOf"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
else {
errors = _errs0;
if(vErrors !== null){
if(_errs0){
vErrors.length = _errs0;
}
else {
vErrors = null;
}
}
}
validate28.errors = vErrors;
evaluated0.props = props0;
return errors === 0;
}
validate28.evaluated = {"dynamicProps":true,"dynamicItems":false};

const schema80 = {"type":"object","additionalProperties":false,"required":["id","kind","entityIds","driving","sourceEvidence","confidence","locked"],"properties":{"id":{"$ref":"#/$defs/identifier"},"kind":{"enum":["horizontal","vertical","coincident","parallel","perpendicular","equalLength","equalRadius","concentric","tangent","symmetric","fixed","distance","horizontalDistance","verticalDistance","angle","radius","diameter"]},"entityIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"value":{"type":["number","null"]},"measuredValue":{"type":["number","null"]},"suggestedNominalValue":{"type":["number","null"]},"nominalAccepted":{"type":["boolean","null"]},"unit":{"enum":["length","angle","none",null]},"driving":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"}}};

function validate61(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate61.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.kind === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "kind"},message:"must have required property '"+"kind"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.entityIds === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "entityIds"},message:"must have required property '"+"entityIds"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.driving === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "driving"},message:"must have required property '"+"driving"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.confidence === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.locked === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "locked"},message:"must have required property '"+"locked"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema80.properties, key0))){
const err7 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err8 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(func2(data0) < 1){
const err9 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(!pattern4.test(data0)){
const err10 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.kind !== undefined){
let data1 = data.kind;
if(!(((((((((((((((((data1 === "horizontal") || (data1 === "vertical")) || (data1 === "coincident")) || (data1 === "parallel")) || (data1 === "perpendicular")) || (data1 === "equalLength")) || (data1 === "equalRadius")) || (data1 === "concentric")) || (data1 === "tangent")) || (data1 === "symmetric")) || (data1 === "fixed")) || (data1 === "distance")) || (data1 === "horizontalDistance")) || (data1 === "verticalDistance")) || (data1 === "angle")) || (data1 === "radius")) || (data1 === "diameter"))){
const err12 = {instancePath:instancePath+"/kind",schemaPath:"#/properties/kind/enum",keyword:"enum",params:{allowedValues: schema80.properties.kind.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data.entityIds !== undefined){
let data2 = data.entityIds;
if(Array.isArray(data2)){
if(data2.length < 1){
const err13 = {instancePath:instancePath+"/entityIds",schemaPath:"#/properties/entityIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
let data3 = data2[i0];
if(typeof data3 === "string"){
if(func2(data3) > 160){
const err14 = {instancePath:instancePath+"/entityIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(func2(data3) < 1){
const err15 = {instancePath:instancePath+"/entityIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
if(!pattern4.test(data3)){
const err16 = {instancePath:instancePath+"/entityIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
else {
const err17 = {instancePath:instancePath+"/entityIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
let i1 = data2.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data2[i1], data2[j0])){
const err18 = {instancePath:instancePath+"/entityIds",schemaPath:"#/properties/entityIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err19 = {instancePath:instancePath+"/entityIds",schemaPath:"#/properties/entityIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data.value !== undefined){
let data4 = data.value;
if((!((typeof data4 == "number") && (isFinite(data4)))) && (data4 !== null)){
const err20 = {instancePath:instancePath+"/value",schemaPath:"#/properties/value/type",keyword:"type",params:{type: schema80.properties.value.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.measuredValue !== undefined){
let data5 = data.measuredValue;
if((!((typeof data5 == "number") && (isFinite(data5)))) && (data5 !== null)){
const err21 = {instancePath:instancePath+"/measuredValue",schemaPath:"#/properties/measuredValue/type",keyword:"type",params:{type: schema80.properties.measuredValue.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data.suggestedNominalValue !== undefined){
let data6 = data.suggestedNominalValue;
if((!((typeof data6 == "number") && (isFinite(data6)))) && (data6 !== null)){
const err22 = {instancePath:instancePath+"/suggestedNominalValue",schemaPath:"#/properties/suggestedNominalValue/type",keyword:"type",params:{type: schema80.properties.suggestedNominalValue.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data.nominalAccepted !== undefined){
let data7 = data.nominalAccepted;
if((typeof data7 !== "boolean") && (data7 !== null)){
const err23 = {instancePath:instancePath+"/nominalAccepted",schemaPath:"#/properties/nominalAccepted/type",keyword:"type",params:{type: schema80.properties.nominalAccepted.type},message:"must be boolean,null"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.unit !== undefined){
let data8 = data.unit;
if(!((((data8 === "length") || (data8 === "angle")) || (data8 === "none")) || (data8 === null))){
const err24 = {instancePath:instancePath+"/unit",schemaPath:"#/properties/unit/enum",keyword:"enum",params:{allowedValues: schema80.properties.unit.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data.driving !== undefined){
if(typeof data.driving !== "boolean"){
const err25 = {instancePath:instancePath+"/driving",schemaPath:"#/properties/driving/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data10 = data.sourceEvidence;
if(Array.isArray(data10)){
const len1 = data10.length;
for(let i2=0; i2<len1; i2++){
let data11 = data10[i2];
if(typeof data11 === "string"){
if(func2(data11) > 160){
const err26 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
if(func2(data11) < 1){
const err27 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
if(!pattern4.test(data11)){
const err28 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
else {
const err29 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
let i3 = data10.length;
let j1;
if(i3 > 1){
outer1:
for(;i3--;){
for(j1 = i3; j1--;){
if(func0(data10[i3], data10[j1])){
const err30 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/uniqueItems",keyword:"uniqueItems",params:{i: i3, j: j1},message:"must NOT have duplicate items (items ## "+j1+" and "+i3+" are identical)"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
break outer1;
}
}
}
}
}
else {
const err31 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data.confidence !== undefined){
let data12 = data.confidence;
if((typeof data12 == "number") && (isFinite(data12))){
if(data12 > 1 || isNaN(data12)){
const err32 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(data12 < 0 || isNaN(data12)){
const err33 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
else {
const err34 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
if(data.locked !== undefined){
if(typeof data.locked !== "boolean"){
const err35 = {instancePath:instancePath+"/locked",schemaPath:"#/properties/locked/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
}
else {
const err36 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
validate61.errors = vErrors;
return errors === 0;
}
validate61.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema85 = {"type":"object","additionalProperties":false,"required":["id","outerLoop","innerLoops","orientation","closed","sourceEvidence","confidence","locked"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":["string","null"],"maxLength":200},"outerLoop":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}},"innerLoops":{"type":"array","items":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"}}},"orientation":{"enum":["clockwise","counterclockwise"]},"closed":{"const":true},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"locked":{"type":"boolean"}}};

function validate63(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate63.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.outerLoop === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "outerLoop"},message:"must have required property '"+"outerLoop"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.innerLoops === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "innerLoops"},message:"must have required property '"+"innerLoops"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.orientation === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "orientation"},message:"must have required property '"+"orientation"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.closed === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "closed"},message:"must have required property '"+"closed"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.confidence === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.locked === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "locked"},message:"must have required property '"+"locked"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema85.properties, key0))){
const err8 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err9 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(func2(data0) < 1){
const err10 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(!pattern4.test(data0)){
const err11 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
else {
const err12 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data.name !== undefined){
let data1 = data.name;
if((typeof data1 !== "string") && (data1 !== null)){
const err13 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/type",keyword:"type",params:{type: schema85.properties.name.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(typeof data1 === "string"){
if(func2(data1) > 200){
const err14 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
if(data.outerLoop !== undefined){
let data2 = data.outerLoop;
if(Array.isArray(data2)){
if(data2.length < 1){
const err15 = {instancePath:instancePath+"/outerLoop",schemaPath:"#/properties/outerLoop/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
let data3 = data2[i0];
if(typeof data3 === "string"){
if(func2(data3) > 160){
const err16 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(func2(data3) < 1){
const err17 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(!pattern4.test(data3)){
const err18 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
else {
const err19 = {instancePath:instancePath+"/outerLoop/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
else {
const err20 = {instancePath:instancePath+"/outerLoop",schemaPath:"#/properties/outerLoop/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.innerLoops !== undefined){
let data4 = data.innerLoops;
if(Array.isArray(data4)){
const len1 = data4.length;
for(let i1=0; i1<len1; i1++){
let data5 = data4[i1];
if(Array.isArray(data5)){
if(data5.length < 1){
const err21 = {instancePath:instancePath+"/innerLoops/" + i1,schemaPath:"#/properties/innerLoops/items/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
const len2 = data5.length;
for(let i2=0; i2<len2; i2++){
let data6 = data5[i2];
if(typeof data6 === "string"){
if(func2(data6) > 160){
const err22 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
if(func2(data6) < 1){
const err23 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
if(!pattern4.test(data6)){
const err24 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
else {
const err25 = {instancePath:instancePath+"/innerLoops/" + i1+"/" + i2,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
else {
const err26 = {instancePath:instancePath+"/innerLoops/" + i1,schemaPath:"#/properties/innerLoops/items/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
}
else {
const err27 = {instancePath:instancePath+"/innerLoops",schemaPath:"#/properties/innerLoops/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.orientation !== undefined){
let data7 = data.orientation;
if(!((data7 === "clockwise") || (data7 === "counterclockwise"))){
const err28 = {instancePath:instancePath+"/orientation",schemaPath:"#/properties/orientation/enum",keyword:"enum",params:{allowedValues: schema85.properties.orientation.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
if(data.closed !== undefined){
if(true !== data.closed){
const err29 = {instancePath:instancePath+"/closed",schemaPath:"#/properties/closed/const",keyword:"const",params:{allowedValue: true},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data9 = data.sourceEvidence;
if(Array.isArray(data9)){
const len3 = data9.length;
for(let i3=0; i3<len3; i3++){
let data10 = data9[i3];
if(typeof data10 === "string"){
if(func2(data10) > 160){
const err30 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
if(func2(data10) < 1){
const err31 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
if(!pattern4.test(data10)){
const err32 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
}
else {
const err33 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
let i4 = data9.length;
let j0;
if(i4 > 1){
outer0:
for(;i4--;){
for(j0 = i4; j0--;){
if(func0(data9[i4], data9[j0])){
const err34 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/uniqueItems",keyword:"uniqueItems",params:{i: i4, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i4+" are identical)"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err35 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
if(data.confidence !== undefined){
let data11 = data.confidence;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 > 1 || isNaN(data11)){
const err36 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
if(data11 < 0 || isNaN(data11)){
const err37 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
}
else {
const err38 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
if(data.locked !== undefined){
if(typeof data.locked !== "boolean"){
const err39 = {instancePath:instancePath+"/locked",schemaPath:"#/properties/locked/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
}
else {
const err40 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
validate63.errors = vErrors;
return errors === 0;
}
validate63.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema93 = {"type":"object","additionalProperties":false,"required":["target","locked","reason"],"properties":{"target":{"$ref":"#/$defs/identifier"},"locked":{"type":"boolean"},"reason":{"type":"string","maxLength":1000},"lockedAt":{"$ref":"#/$defs/nullableTimestamp"},"lockedBy":{"type":["string","null"],"maxLength":200}}};
const schema95 = {"type":["string","null"],"format":"date-time"};
const formats0 = fullFormats["date-time"];

function validate65(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate65.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.target === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "target"},message:"must have required property '"+"target"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.locked === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "locked"},message:"must have required property '"+"locked"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.reason === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "reason"},message:"must have required property '"+"reason"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
for(const key0 in data){
if(!(((((key0 === "target") || (key0 === "locked")) || (key0 === "reason")) || (key0 === "lockedAt")) || (key0 === "lockedBy"))){
const err3 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.target !== undefined){
let data0 = data.target;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err4 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(func2(data0) < 1){
const err5 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(!pattern4.test(data0)){
const err6 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.locked !== undefined){
if(typeof data.locked !== "boolean"){
const err8 = {instancePath:instancePath+"/locked",schemaPath:"#/properties/locked/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.reason !== undefined){
let data2 = data.reason;
if(typeof data2 === "string"){
if(func2(data2) > 1000){
const err9 = {instancePath:instancePath+"/reason",schemaPath:"#/properties/reason/maxLength",keyword:"maxLength",params:{limit: 1000},message:"must NOT have more than 1000 characters"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/reason",schemaPath:"#/properties/reason/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.lockedAt !== undefined){
let data3 = data.lockedAt;
if((typeof data3 !== "string") && (data3 !== null)){
const err11 = {instancePath:instancePath+"/lockedAt",schemaPath:"#/$defs/nullableTimestamp/type",keyword:"type",params:{type: schema95.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(typeof data3 === "string"){
if(!(formats0.validate(data3))){
const err12 = {instancePath:instancePath+"/lockedAt",schemaPath:"#/$defs/nullableTimestamp/format",keyword:"format",params:{format: "date-time"},message:"must match format \""+"date-time"+"\""};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
if(data.lockedBy !== undefined){
let data4 = data.lockedBy;
if((typeof data4 !== "string") && (data4 !== null)){
const err13 = {instancePath:instancePath+"/lockedBy",schemaPath:"#/properties/lockedBy/type",keyword:"type",params:{type: schema93.properties.lockedBy.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(typeof data4 === "string"){
if(func2(data4) > 200){
const err14 = {instancePath:instancePath+"/lockedBy",schemaPath:"#/properties/lockedBy/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
}
else {
const err15 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
validate65.errors = vErrors;
return errors === 0;
}
validate65.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema96 = {"type":"object","additionalProperties":false,"required":["target","value","reason"],"properties":{"target":{"$ref":"#/$defs/identifier"},"value":{"$ref":"#/$defs/jsonValue"},"previousValue":{"$ref":"#/$defs/jsonValue"},"reason":{"type":"string","maxLength":1000},"createdAt":{"$ref":"#/$defs/nullableTimestamp"},"createdBy":{"type":["string","null"],"maxLength":200}}};
const schema98 = {"oneOf":[{"type":"null"},{"type":"boolean"},{"type":"number"},{"type":"string"},{"type":"array","items":{"$ref":"#/$defs/jsonValue"}},{"type":"object","additionalProperties":{"$ref":"#/$defs/jsonValue"}}]};
const wrapper0 = {validate: validate68};

function validate68(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate68.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
const _errs0 = errors;
let valid0 = false;
let passing0 = null;
const _errs1 = errors;
if(data !== null){
const err0 = {instancePath,schemaPath:"#/oneOf/0/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
var _valid0 = _errs1 === errors;
if(_valid0){
valid0 = true;
passing0 = 0;
}
const _errs3 = errors;
if(typeof data !== "boolean"){
const err1 = {instancePath,schemaPath:"#/oneOf/1/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
var _valid0 = _errs3 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 1];
}
else {
if(_valid0){
valid0 = true;
passing0 = 1;
}
const _errs5 = errors;
if(!((typeof data == "number") && (isFinite(data)))){
const err2 = {instancePath,schemaPath:"#/oneOf/2/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
var _valid0 = _errs5 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 2];
}
else {
if(_valid0){
valid0 = true;
passing0 = 2;
}
const _errs7 = errors;
if(typeof data !== "string"){
const err3 = {instancePath,schemaPath:"#/oneOf/3/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
var _valid0 = _errs7 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 3];
}
else {
if(_valid0){
valid0 = true;
passing0 = 3;
}
const _errs9 = errors;
if(Array.isArray(data)){
const len0 = data.length;
for(let i0=0; i0<len0; i0++){
if(!(wrapper0.validate(data[i0], {instancePath:instancePath+"/" + i0,parentData:data,parentDataProperty:i0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? wrapper0.validate.errors : vErrors.concat(wrapper0.validate.errors);
errors = vErrors.length;
}
}
}
else {
const err4 = {instancePath,schemaPath:"#/oneOf/4/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
var _valid0 = _errs9 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 4];
}
else {
if(_valid0){
valid0 = true;
passing0 = 4;
var items1 = true;
}
const _errs12 = errors;
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if(!(wrapper0.validate(data[key0], {instancePath:instancePath+"/" + key0.replace(/~/g, "~0").replace(/\//g, "~1"),parentData:data,parentDataProperty:key0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? wrapper0.validate.errors : vErrors.concat(wrapper0.validate.errors);
errors = vErrors.length;
}
}
}
else {
const err5 = {instancePath,schemaPath:"#/oneOf/5/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
var _valid0 = _errs12 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 5];
}
else {
if(_valid0){
valid0 = true;
passing0 = 5;
var props2 = true;
}
}
}
}
}
}
if(!valid0){
const err6 = {instancePath,schemaPath:"#/oneOf",keyword:"oneOf",params:{passingSchemas: passing0},message:"must match exactly one schema in oneOf"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
else {
errors = _errs0;
if(vErrors !== null){
if(_errs0){
vErrors.length = _errs0;
}
else {
vErrors = null;
}
}
}
validate68.errors = vErrors;
evaluated0.props = props2;
evaluated0.items = items1;
return errors === 0;
}
validate68.evaluated = {"dynamicProps":true,"dynamicItems":true};


function validate67(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate67.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.target === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "target"},message:"must have required property '"+"target"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.value === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "value"},message:"must have required property '"+"value"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.reason === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "reason"},message:"must have required property '"+"reason"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
for(const key0 in data){
if(!((((((key0 === "target") || (key0 === "value")) || (key0 === "previousValue")) || (key0 === "reason")) || (key0 === "createdAt")) || (key0 === "createdBy"))){
const err3 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.target !== undefined){
let data0 = data.target;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err4 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(func2(data0) < 1){
const err5 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(!pattern4.test(data0)){
const err6 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/target",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.value !== undefined){
if(!(validate68(data.value, {instancePath:instancePath+"/value",parentData:data,parentDataProperty:"value",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate68.errors : vErrors.concat(validate68.errors);
errors = vErrors.length;
}
}
if(data.previousValue !== undefined){
if(!(validate68(data.previousValue, {instancePath:instancePath+"/previousValue",parentData:data,parentDataProperty:"previousValue",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate68.errors : vErrors.concat(validate68.errors);
errors = vErrors.length;
}
}
if(data.reason !== undefined){
let data3 = data.reason;
if(typeof data3 === "string"){
if(func2(data3) > 1000){
const err8 = {instancePath:instancePath+"/reason",schemaPath:"#/properties/reason/maxLength",keyword:"maxLength",params:{limit: 1000},message:"must NOT have more than 1000 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
else {
const err9 = {instancePath:instancePath+"/reason",schemaPath:"#/properties/reason/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.createdAt !== undefined){
let data4 = data.createdAt;
if((typeof data4 !== "string") && (data4 !== null)){
const err10 = {instancePath:instancePath+"/createdAt",schemaPath:"#/$defs/nullableTimestamp/type",keyword:"type",params:{type: schema95.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(typeof data4 === "string"){
if(!(formats0.validate(data4))){
const err11 = {instancePath:instancePath+"/createdAt",schemaPath:"#/$defs/nullableTimestamp/format",keyword:"format",params:{format: "date-time"},message:"must match format \""+"date-time"+"\""};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
if(data.createdBy !== undefined){
let data5 = data.createdBy;
if((typeof data5 !== "string") && (data5 !== null)){
const err12 = {instancePath:instancePath+"/createdBy",schemaPath:"#/properties/createdBy/type",keyword:"type",params:{type: schema96.properties.createdBy.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(typeof data5 === "string"){
if(func2(data5) > 200){
const err13 = {instancePath:instancePath+"/createdBy",schemaPath:"#/properties/createdBy/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
}
else {
const err14 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
validate67.errors = vErrors;
return errors === 0;
}
validate67.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate25(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate25.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.name === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "name"},message:"must have required property '"+"name"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.plane === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "plane"},message:"must have required property '"+"plane"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.entities === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "entities"},message:"must have required property '"+"entities"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.constraints === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "constraints"},message:"must have required property '"+"constraints"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.profiles === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "profiles"},message:"must have required property '"+"profiles"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.confidence === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data.userLocks === undefined){
const err8 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "userLocks"},message:"must have required property '"+"userLocks"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data.overrides === undefined){
const err9 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "overrides"},message:"must have required property '"+"overrides"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data.suppressed === undefined){
const err10 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "suppressed"},message:"must have required property '"+"suppressed"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema45.properties, key0))){
const err11 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err12 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(func2(data0) < 1){
const err13 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(!pattern4.test(data0)){
const err14 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.name !== undefined){
let data1 = data.name;
if(typeof data1 === "string"){
if(func2(data1) > 200){
const err16 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(func2(data1) < 1){
const err17 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
else {
const err18 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.plane !== undefined){
if(!(validate26(data.plane, {instancePath:instancePath+"/plane",parentData:data,parentDataProperty:"plane",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate26.errors : vErrors.concat(validate26.errors);
errors = vErrors.length;
}
}
if(data.entities !== undefined){
let data3 = data.entities;
if(Array.isArray(data3)){
const len0 = data3.length;
for(let i0=0; i0<len0; i0++){
if(!(validate28(data3[i0], {instancePath:instancePath+"/entities/" + i0,parentData:data3,parentDataProperty:i0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate28.errors : vErrors.concat(validate28.errors);
errors = vErrors.length;
}
}
}
else {
const err19 = {instancePath:instancePath+"/entities",schemaPath:"#/properties/entities/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data.constraints !== undefined){
let data5 = data.constraints;
if(Array.isArray(data5)){
const len1 = data5.length;
for(let i1=0; i1<len1; i1++){
if(!(validate61(data5[i1], {instancePath:instancePath+"/constraints/" + i1,parentData:data5,parentDataProperty:i1,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate61.errors : vErrors.concat(validate61.errors);
errors = vErrors.length;
}
}
}
else {
const err20 = {instancePath:instancePath+"/constraints",schemaPath:"#/properties/constraints/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.profiles !== undefined){
let data7 = data.profiles;
if(Array.isArray(data7)){
const len2 = data7.length;
for(let i2=0; i2<len2; i2++){
if(!(validate63(data7[i2], {instancePath:instancePath+"/profiles/" + i2,parentData:data7,parentDataProperty:i2,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate63.errors : vErrors.concat(validate63.errors);
errors = vErrors.length;
}
}
}
else {
const err21 = {instancePath:instancePath+"/profiles",schemaPath:"#/properties/profiles/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data9 = data.sourceEvidence;
if(Array.isArray(data9)){
const len3 = data9.length;
for(let i3=0; i3<len3; i3++){
let data10 = data9[i3];
if(typeof data10 === "string"){
if(func2(data10) > 160){
const err22 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
if(func2(data10) < 1){
const err23 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
if(!pattern4.test(data10)){
const err24 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
else {
const err25 = {instancePath:instancePath+"/sourceEvidence/" + i3,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
let i4 = data9.length;
let j0;
if(i4 > 1){
outer0:
for(;i4--;){
for(j0 = i4; j0--;){
if(func0(data9[i4], data9[j0])){
const err26 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/uniqueItems",keyword:"uniqueItems",params:{i: i4, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i4+" are identical)"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err27 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.confidence !== undefined){
let data11 = data.confidence;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 > 1 || isNaN(data11)){
const err28 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if(data11 < 0 || isNaN(data11)){
const err29 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
else {
const err30 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
if(data.userLocks !== undefined){
let data12 = data.userLocks;
if(Array.isArray(data12)){
const len4 = data12.length;
for(let i5=0; i5<len4; i5++){
if(!(validate65(data12[i5], {instancePath:instancePath+"/userLocks/" + i5,parentData:data12,parentDataProperty:i5,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate65.errors : vErrors.concat(validate65.errors);
errors = vErrors.length;
}
}
}
else {
const err31 = {instancePath:instancePath+"/userLocks",schemaPath:"#/properties/userLocks/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data.overrides !== undefined){
let data14 = data.overrides;
if(Array.isArray(data14)){
const len5 = data14.length;
for(let i6=0; i6<len5; i6++){
if(!(validate67(data14[i6], {instancePath:instancePath+"/overrides/" + i6,parentData:data14,parentDataProperty:i6,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate67.errors : vErrors.concat(validate67.errors);
errors = vErrors.length;
}
}
}
else {
const err32 = {instancePath:instancePath+"/overrides",schemaPath:"#/properties/overrides/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
}
if(data.suppressed !== undefined){
if(typeof data.suppressed !== "boolean"){
const err33 = {instancePath:instancePath+"/suppressed",schemaPath:"#/properties/suppressed/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
}
else {
const err34 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
validate25.errors = vErrors;
return errors === 0;
}
validate25.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema100 = {"oneOf":[{"$ref":"#/$defs/extrusionFeature"},{"$ref":"#/$defs/pocketFeature"},{"$ref":"#/$defs/holeFeature"},{"$ref":"#/$defs/counterboreFeature"},{"$ref":"#/$defs/countersinkFeature"},{"$ref":"#/$defs/revolutionFeature"},{"$ref":"#/$defs/linearPatternFeature"},{"$ref":"#/$defs/circularPatternFeature"},{"$ref":"#/$defs/mirrorFeature"},{"$ref":"#/$defs/chamferFeature"},{"$ref":"#/$defs/filletFeature"},{"$ref":"#/$defs/importedFacetedFeature"}]};
const schema101 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","direction","extent"],"properties":{"operation":{"const":"extrusion"},"booleanMode":{"enum":["base","additive","subtractive"]},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"extent":{"enum":["blind","symmetric","throughAll","toFace"]},"distance":{"type":["number","null"],"exclusiveMinimum":0},"targetFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false};
const schema102 = {"type":"object","required":["id","name","operation","order","dependencies","suppressed","sourceEvidence","confidence","userLocks","overrides","semanticOutputs"],"properties":{"id":{"$ref":"#/$defs/identifier"},"name":{"type":"string","minLength":1,"maxLength":200},"operation":{"type":"string"},"order":{"type":"integer","minimum":0},"dependencies":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"suppressed":{"type":"boolean"},"sourceEvidence":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"confidence":{"$ref":"#/$defs/confidence"},"userLocks":{"type":"array","items":{"$ref":"#/$defs/userLock"}},"overrides":{"type":"array","items":{"$ref":"#/$defs/userOverride"}},"semanticOutputs":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true}}};

function validate75(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate75.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.name === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "name"},message:"must have required property '"+"name"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.operation === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "operation"},message:"must have required property '"+"operation"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.order === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "order"},message:"must have required property '"+"order"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.dependencies === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "dependencies"},message:"must have required property '"+"dependencies"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.suppressed === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "suppressed"},message:"must have required property '"+"suppressed"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.confidence === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data.userLocks === undefined){
const err8 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "userLocks"},message:"must have required property '"+"userLocks"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data.overrides === undefined){
const err9 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "overrides"},message:"must have required property '"+"overrides"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data.semanticOutputs === undefined){
const err10 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "semanticOutputs"},message:"must have required property '"+"semanticOutputs"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err11 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(func2(data0) < 1){
const err12 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(!pattern4.test(data0)){
const err13 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
else {
const err14 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data.name !== undefined){
let data1 = data.name;
if(typeof data1 === "string"){
if(func2(data1) > 200){
const err15 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
if(func2(data1) < 1){
const err16 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
else {
const err17 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.operation !== undefined){
if(typeof data.operation !== "string"){
const err18 = {instancePath:instancePath+"/operation",schemaPath:"#/properties/operation/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.order !== undefined){
let data3 = data.order;
if(!(((typeof data3 == "number") && (!(data3 % 1) && !isNaN(data3))) && (isFinite(data3)))){
const err19 = {instancePath:instancePath+"/order",schemaPath:"#/properties/order/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if((typeof data3 == "number") && (isFinite(data3))){
if(data3 < 0 || isNaN(data3)){
const err20 = {instancePath:instancePath+"/order",schemaPath:"#/properties/order/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
}
if(data.dependencies !== undefined){
let data4 = data.dependencies;
if(Array.isArray(data4)){
const len0 = data4.length;
for(let i0=0; i0<len0; i0++){
let data5 = data4[i0];
if(typeof data5 === "string"){
if(func2(data5) > 160){
const err21 = {instancePath:instancePath+"/dependencies/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(func2(data5) < 1){
const err22 = {instancePath:instancePath+"/dependencies/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
if(!pattern4.test(data5)){
const err23 = {instancePath:instancePath+"/dependencies/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
else {
const err24 = {instancePath:instancePath+"/dependencies/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
let i1 = data4.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data4[i1], data4[j0])){
const err25 = {instancePath:instancePath+"/dependencies",schemaPath:"#/properties/dependencies/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err26 = {instancePath:instancePath+"/dependencies",schemaPath:"#/properties/dependencies/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.suppressed !== undefined){
if(typeof data.suppressed !== "boolean"){
const err27 = {instancePath:instancePath+"/suppressed",schemaPath:"#/properties/suppressed/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data7 = data.sourceEvidence;
if(Array.isArray(data7)){
const len1 = data7.length;
for(let i2=0; i2<len1; i2++){
let data8 = data7[i2];
if(typeof data8 === "string"){
if(func2(data8) > 160){
const err28 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if(func2(data8) < 1){
const err29 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
if(!pattern4.test(data8)){
const err30 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
else {
const err31 = {instancePath:instancePath+"/sourceEvidence/" + i2,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
let i3 = data7.length;
let j1;
if(i3 > 1){
outer1:
for(;i3--;){
for(j1 = i3; j1--;){
if(func0(data7[i3], data7[j1])){
const err32 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/uniqueItems",keyword:"uniqueItems",params:{i: i3, j: j1},message:"must NOT have duplicate items (items ## "+j1+" and "+i3+" are identical)"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
break outer1;
}
}
}
}
}
else {
const err33 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
if(data.confidence !== undefined){
let data9 = data.confidence;
if((typeof data9 == "number") && (isFinite(data9))){
if(data9 > 1 || isNaN(data9)){
const err34 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
if(data9 < 0 || isNaN(data9)){
const err35 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
else {
const err36 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
}
if(data.userLocks !== undefined){
let data10 = data.userLocks;
if(Array.isArray(data10)){
const len2 = data10.length;
for(let i4=0; i4<len2; i4++){
if(!(validate65(data10[i4], {instancePath:instancePath+"/userLocks/" + i4,parentData:data10,parentDataProperty:i4,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate65.errors : vErrors.concat(validate65.errors);
errors = vErrors.length;
}
}
}
else {
const err37 = {instancePath:instancePath+"/userLocks",schemaPath:"#/properties/userLocks/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
}
if(data.overrides !== undefined){
let data12 = data.overrides;
if(Array.isArray(data12)){
const len3 = data12.length;
for(let i5=0; i5<len3; i5++){
if(!(validate67(data12[i5], {instancePath:instancePath+"/overrides/" + i5,parentData:data12,parentDataProperty:i5,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate67.errors : vErrors.concat(validate67.errors);
errors = vErrors.length;
}
}
}
else {
const err38 = {instancePath:instancePath+"/overrides",schemaPath:"#/properties/overrides/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
if(data.semanticOutputs !== undefined){
let data14 = data.semanticOutputs;
if(Array.isArray(data14)){
const len4 = data14.length;
for(let i6=0; i6<len4; i6++){
let data15 = data14[i6];
if(typeof data15 === "string"){
if(func2(data15) > 160){
const err39 = {instancePath:instancePath+"/semanticOutputs/" + i6,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
if(func2(data15) < 1){
const err40 = {instancePath:instancePath+"/semanticOutputs/" + i6,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
if(!pattern4.test(data15)){
const err41 = {instancePath:instancePath+"/semanticOutputs/" + i6,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
}
else {
const err42 = {instancePath:instancePath+"/semanticOutputs/" + i6,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
}
let i7 = data14.length;
let j2;
if(i7 > 1){
outer2:
for(;i7--;){
for(j2 = i7; j2--;){
if(func0(data14[i7], data14[j2])){
const err43 = {instancePath:instancePath+"/semanticOutputs",schemaPath:"#/properties/semanticOutputs/uniqueItems",keyword:"uniqueItems",params:{i: i7, j: j2},message:"must NOT have duplicate items (items ## "+j2+" and "+i7+" are identical)"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
break outer2;
}
}
}
}
}
else {
const err44 = {instancePath:instancePath+"/semanticOutputs",schemaPath:"#/properties/semanticOutputs/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
}
}
else {
const err45 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
validate75.errors = vErrors;
return errors === 0;
}
validate75.evaluated = {"props":{"id":true,"name":true,"operation":true,"order":true,"dependencies":true,"suppressed":true,"sourceEvidence":true,"confidence":true,"userLocks":true,"overrides":true,"semanticOutputs":true},"dynamicProps":false,"dynamicItems":false};

const schema111 = {"anyOf":[{"$ref":"#/$defs/identifier"},{"type":"null"}]};

function validate79(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate79.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
const _errs0 = errors;
let valid0 = false;
const _errs1 = errors;
if(typeof data === "string"){
if(func2(data) > 160){
const err0 = {instancePath,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(func2(data) < 1){
const err1 = {instancePath,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(!pattern4.test(data)){
const err2 = {instancePath,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
else {
const err3 = {instancePath,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
var _valid0 = _errs1 === errors;
valid0 = valid0 || _valid0;
const _errs4 = errors;
if(data !== null){
const err4 = {instancePath,schemaPath:"#/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
var _valid0 = _errs4 === errors;
valid0 = valid0 || _valid0;
if(!valid0){
const err5 = {instancePath,schemaPath:"#/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
else {
errors = _errs0;
if(vErrors !== null){
if(_errs0){
vErrors.length = _errs0;
}
else {
vErrors = null;
}
}
}
validate79.errors = vErrors;
return errors === 0;
}
validate79.evaluated = {"dynamicProps":false,"dynamicItems":false};


function validate74(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate74.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sketchId === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sketchId"},message:"must have required property '"+"sketchId"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.profileIds === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "profileIds"},message:"must have required property '"+"profileIds"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.direction === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.extent === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "extent"},message:"must have required property '"+"extent"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.operation !== undefined){
if("extrusion" !== data.operation){
const err5 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "extrusion"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.booleanMode !== undefined){
let data1 = data.booleanMode;
if(!(((data1 === "base") || (data1 === "additive")) || (data1 === "subtractive"))){
const err6 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/enum",keyword:"enum",params:{allowedValues: schema101.allOf[1].properties.booleanMode.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.sketchId !== undefined){
let data2 = data.sketchId;
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err7 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(func2(data2) < 1){
const err8 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(!pattern4.test(data2)){
const err9 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.profileIds !== undefined){
let data3 = data.profileIds;
if(Array.isArray(data3)){
if(data3.length < 1){
const err11 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
const len0 = data3.length;
for(let i0=0; i0<len0; i0++){
let data4 = data3[i0];
if(typeof data4 === "string"){
if(func2(data4) > 160){
const err12 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(func2(data4) < 1){
const err13 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(!pattern4.test(data4)){
const err14 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
let i1 = data3.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data3[i1], data3[j0])){
const err16 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err17 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.direction !== undefined){
let data5 = data.direction;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.x === undefined){
const err18 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data5.y === undefined){
const err19 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(data5.z === undefined){
const err20 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
for(const key0 in data5){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err21 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data5.x !== undefined){
let data6 = data5.x;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err22 = {instancePath:instancePath+"/direction/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data5.y !== undefined){
let data7 = data5.y;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err23 = {instancePath:instancePath+"/direction/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data5.z !== undefined){
let data8 = data5.z;
if(!((typeof data8 == "number") && (isFinite(data8)))){
const err24 = {instancePath:instancePath+"/direction/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
}
else {
const err25 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.extent !== undefined){
let data9 = data.extent;
if(!((((data9 === "blind") || (data9 === "symmetric")) || (data9 === "throughAll")) || (data9 === "toFace"))){
const err26 = {instancePath:instancePath+"/extent",schemaPath:"#/allOf/1/properties/extent/enum",keyword:"enum",params:{allowedValues: schema101.allOf[1].properties.extent.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.distance !== undefined){
let data10 = data.distance;
if((!((typeof data10 == "number") && (isFinite(data10)))) && (data10 !== null)){
const err27 = {instancePath:instancePath+"/distance",schemaPath:"#/allOf/1/properties/distance/type",keyword:"type",params:{type: schema101.allOf[1].properties.distance.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
if((typeof data10 == "number") && (isFinite(data10))){
if(data10 <= 0 || isNaN(data10)){
const err28 = {instancePath:instancePath+"/distance",schemaPath:"#/allOf/1/properties/distance/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
}
if(data.targetFace !== undefined){
if(!(validate79(data.targetFace, {instancePath:instancePath+"/targetFace",parentData:data,parentDataProperty:"targetFace",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
}
else {
const err29 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if((((((((((((((((((key1 !== "operation") && (key1 !== "booleanMode")) && (key1 !== "sketchId")) && (key1 !== "profileIds")) && (key1 !== "direction")) && (key1 !== "extent")) && (key1 !== "distance")) && (key1 !== "targetFace")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "order")) && (key1 !== "dependencies")) && (key1 !== "suppressed")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "userLocks")) && (key1 !== "overrides")) && (key1 !== "semanticOutputs")){
const err30 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
}
validate74.errors = vErrors;
return errors === 0;
}
validate74.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema113 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","direction","extent","depth"],"properties":{"operation":{"const":"pocket"},"booleanMode":{"const":"subtractive"},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"extent":{"enum":["blind","throughAll","toFace"]},"depth":{"type":"number","exclusiveMinimum":0},"targetFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false};

function validate82(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate82.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sketchId === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sketchId"},message:"must have required property '"+"sketchId"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.profileIds === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "profileIds"},message:"must have required property '"+"profileIds"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.direction === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.extent === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "extent"},message:"must have required property '"+"extent"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.depth === undefined){
const err5 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "depth"},message:"must have required property '"+"depth"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.operation !== undefined){
if("pocket" !== data.operation){
const err6 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "pocket"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.booleanMode !== undefined){
if("subtractive" !== data.booleanMode){
const err7 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/const",keyword:"const",params:{allowedValue: "subtractive"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.sketchId !== undefined){
let data2 = data.sketchId;
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err8 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(func2(data2) < 1){
const err9 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(!pattern4.test(data2)){
const err10 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.profileIds !== undefined){
let data3 = data.profileIds;
if(Array.isArray(data3)){
if(data3.length < 1){
const err12 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
const len0 = data3.length;
for(let i0=0; i0<len0; i0++){
let data4 = data3[i0];
if(typeof data4 === "string"){
if(func2(data4) > 160){
const err13 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(func2(data4) < 1){
const err14 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(!pattern4.test(data4)){
const err15 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
else {
const err16 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
let i1 = data3.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data3[i1], data3[j0])){
const err17 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err18 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.direction !== undefined){
let data5 = data.direction;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.x === undefined){
const err19 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(data5.y === undefined){
const err20 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if(data5.z === undefined){
const err21 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
for(const key0 in data5){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err22 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data5.x !== undefined){
let data6 = data5.x;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err23 = {instancePath:instancePath+"/direction/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data5.y !== undefined){
let data7 = data5.y;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err24 = {instancePath:instancePath+"/direction/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data5.z !== undefined){
let data8 = data5.z;
if(!((typeof data8 == "number") && (isFinite(data8)))){
const err25 = {instancePath:instancePath+"/direction/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
else {
const err26 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.extent !== undefined){
let data9 = data.extent;
if(!(((data9 === "blind") || (data9 === "throughAll")) || (data9 === "toFace"))){
const err27 = {instancePath:instancePath+"/extent",schemaPath:"#/allOf/1/properties/extent/enum",keyword:"enum",params:{allowedValues: schema113.allOf[1].properties.extent.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.depth !== undefined){
let data10 = data.depth;
if((typeof data10 == "number") && (isFinite(data10))){
if(data10 <= 0 || isNaN(data10)){
const err28 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
else {
const err29 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
if(data.targetFace !== undefined){
if(!(validate79(data.targetFace, {instancePath:instancePath+"/targetFace",parentData:data,parentDataProperty:"targetFace",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
}
else {
const err30 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if((((((((((((((((((key1 !== "operation") && (key1 !== "booleanMode")) && (key1 !== "sketchId")) && (key1 !== "profileIds")) && (key1 !== "direction")) && (key1 !== "extent")) && (key1 !== "depth")) && (key1 !== "targetFace")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "order")) && (key1 !== "dependencies")) && (key1 !== "suppressed")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "userLocks")) && (key1 !== "overrides")) && (key1 !== "semanticOutputs")){
const err31 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
}
validate82.errors = vErrors;
return errors === 0;
}
validate82.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema117 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter"],"properties":{"operation":{"const":"hole"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"terminationFace":{"$ref":"#/$defs/nullableIdentifier"}}}],"unevaluatedProperties":false};

function validate86(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate86.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.holeType === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "holeType"},message:"must have required property '"+"holeType"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.position === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "position"},message:"must have required property '"+"position"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.axis === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "axis"},message:"must have required property '"+"axis"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.diameter === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "diameter"},message:"must have required property '"+"diameter"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.operation !== undefined){
if("hole" !== data.operation){
const err5 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "hole"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.booleanMode !== undefined){
if("subtractive" !== data.booleanMode){
const err6 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/const",keyword:"const",params:{allowedValue: "subtractive"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.holeType !== undefined){
let data2 = data.holeType;
if(!((data2 === "through") || (data2 === "blind"))){
const err7 = {instancePath:instancePath+"/holeType",schemaPath:"#/allOf/1/properties/holeType/enum",keyword:"enum",params:{allowedValues: schema117.allOf[1].properties.holeType.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.position !== undefined){
let data3 = data.position;
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
if(data3.x === undefined){
const err8 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data3.y === undefined){
const err9 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data3.z === undefined){
const err10 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
for(const key0 in data3){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err11 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data3.x !== undefined){
let data4 = data3.x;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err12 = {instancePath:instancePath+"/position/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data3.y !== undefined){
let data5 = data3.y;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err13 = {instancePath:instancePath+"/position/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data3.z !== undefined){
let data6 = data3.z;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err14 = {instancePath:instancePath+"/position/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
}
else {
const err15 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.axis !== undefined){
let data7 = data.axis;
if(data7 && typeof data7 == "object" && !Array.isArray(data7)){
if(data7.x === undefined){
const err16 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data7.y === undefined){
const err17 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(data7.z === undefined){
const err18 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
for(const key1 in data7){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err19 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data7.x !== undefined){
let data8 = data7.x;
if(!((typeof data8 == "number") && (isFinite(data8)))){
const err20 = {instancePath:instancePath+"/axis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data7.y !== undefined){
let data9 = data7.y;
if(!((typeof data9 == "number") && (isFinite(data9)))){
const err21 = {instancePath:instancePath+"/axis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data7.z !== undefined){
let data10 = data7.z;
if(!((typeof data10 == "number") && (isFinite(data10)))){
const err22 = {instancePath:instancePath+"/axis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
}
else {
const err23 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.diameter !== undefined){
let data11 = data.diameter;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 <= 0 || isNaN(data11)){
const err24 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
else {
const err25 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.depth !== undefined){
let data12 = data.depth;
if((!((typeof data12 == "number") && (isFinite(data12)))) && (data12 !== null)){
const err26 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/type",keyword:"type",params:{type: schema117.allOf[1].properties.depth.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
if((typeof data12 == "number") && (isFinite(data12))){
if(data12 <= 0 || isNaN(data12)){
const err27 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
}
if(data.terminationFace !== undefined){
if(!(validate79(data.terminationFace, {instancePath:instancePath+"/terminationFace",parentData:data,parentDataProperty:"terminationFace",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
}
else {
const err28 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if((((((((((((((((((key2 !== "operation") && (key2 !== "booleanMode")) && (key2 !== "holeType")) && (key2 !== "position")) && (key2 !== "axis")) && (key2 !== "diameter")) && (key2 !== "depth")) && (key2 !== "terminationFace")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "order")) && (key2 !== "dependencies")) && (key2 !== "suppressed")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "userLocks")) && (key2 !== "overrides")) && (key2 !== "semanticOutputs")){
const err29 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
}
validate86.errors = vErrors;
return errors === 0;
}
validate86.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema120 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter","boreDiameter","boreDepth"],"properties":{"operation":{"const":"counterbore"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"boreDiameter":{"type":"number","exclusiveMinimum":0},"boreDepth":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false};

function validate90(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate90.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.holeType === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "holeType"},message:"must have required property '"+"holeType"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.position === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "position"},message:"must have required property '"+"position"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.axis === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "axis"},message:"must have required property '"+"axis"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.diameter === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "diameter"},message:"must have required property '"+"diameter"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.boreDiameter === undefined){
const err5 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "boreDiameter"},message:"must have required property '"+"boreDiameter"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.boreDepth === undefined){
const err6 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "boreDepth"},message:"must have required property '"+"boreDepth"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.operation !== undefined){
if("counterbore" !== data.operation){
const err7 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "counterbore"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.booleanMode !== undefined){
if("subtractive" !== data.booleanMode){
const err8 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/const",keyword:"const",params:{allowedValue: "subtractive"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.holeType !== undefined){
let data2 = data.holeType;
if(!((data2 === "through") || (data2 === "blind"))){
const err9 = {instancePath:instancePath+"/holeType",schemaPath:"#/allOf/1/properties/holeType/enum",keyword:"enum",params:{allowedValues: schema120.allOf[1].properties.holeType.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.position !== undefined){
let data3 = data.position;
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
if(data3.x === undefined){
const err10 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data3.y === undefined){
const err11 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(data3.z === undefined){
const err12 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
for(const key0 in data3){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err13 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data3.x !== undefined){
let data4 = data3.x;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err14 = {instancePath:instancePath+"/position/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data3.y !== undefined){
let data5 = data3.y;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err15 = {instancePath:instancePath+"/position/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data3.z !== undefined){
let data6 = data3.z;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err16 = {instancePath:instancePath+"/position/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.axis !== undefined){
let data7 = data.axis;
if(data7 && typeof data7 == "object" && !Array.isArray(data7)){
if(data7.x === undefined){
const err18 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data7.y === undefined){
const err19 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(data7.z === undefined){
const err20 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
for(const key1 in data7){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err21 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data7.x !== undefined){
let data8 = data7.x;
if(!((typeof data8 == "number") && (isFinite(data8)))){
const err22 = {instancePath:instancePath+"/axis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data7.y !== undefined){
let data9 = data7.y;
if(!((typeof data9 == "number") && (isFinite(data9)))){
const err23 = {instancePath:instancePath+"/axis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data7.z !== undefined){
let data10 = data7.z;
if(!((typeof data10 == "number") && (isFinite(data10)))){
const err24 = {instancePath:instancePath+"/axis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
}
else {
const err25 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.diameter !== undefined){
let data11 = data.diameter;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 <= 0 || isNaN(data11)){
const err26 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
else {
const err27 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.depth !== undefined){
let data12 = data.depth;
if((!((typeof data12 == "number") && (isFinite(data12)))) && (data12 !== null)){
const err28 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/type",keyword:"type",params:{type: schema120.allOf[1].properties.depth.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if((typeof data12 == "number") && (isFinite(data12))){
if(data12 <= 0 || isNaN(data12)){
const err29 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
}
if(data.boreDiameter !== undefined){
let data13 = data.boreDiameter;
if((typeof data13 == "number") && (isFinite(data13))){
if(data13 <= 0 || isNaN(data13)){
const err30 = {instancePath:instancePath+"/boreDiameter",schemaPath:"#/allOf/1/properties/boreDiameter/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
else {
const err31 = {instancePath:instancePath+"/boreDiameter",schemaPath:"#/allOf/1/properties/boreDiameter/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data.boreDepth !== undefined){
let data14 = data.boreDepth;
if((typeof data14 == "number") && (isFinite(data14))){
if(data14 <= 0 || isNaN(data14)){
const err32 = {instancePath:instancePath+"/boreDepth",schemaPath:"#/allOf/1/properties/boreDepth/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
}
else {
const err33 = {instancePath:instancePath+"/boreDepth",schemaPath:"#/allOf/1/properties/boreDepth/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
}
else {
const err34 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if(((((((((((((((((((key2 !== "operation") && (key2 !== "booleanMode")) && (key2 !== "holeType")) && (key2 !== "position")) && (key2 !== "axis")) && (key2 !== "diameter")) && (key2 !== "depth")) && (key2 !== "boreDiameter")) && (key2 !== "boreDepth")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "order")) && (key2 !== "dependencies")) && (key2 !== "suppressed")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "userLocks")) && (key2 !== "overrides")) && (key2 !== "semanticOutputs")){
const err35 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
}
validate90.errors = vErrors;
return errors === 0;
}
validate90.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema123 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","holeType","position","axis","diameter","sinkDiameter","sinkAngleDeg"],"properties":{"operation":{"const":"countersink"},"booleanMode":{"const":"subtractive"},"holeType":{"enum":["through","blind"]},"position":{"$ref":"#/$defs/vector3"},"axis":{"$ref":"#/$defs/vector3"},"diameter":{"type":"number","exclusiveMinimum":0},"depth":{"type":["number","null"],"exclusiveMinimum":0},"sinkDiameter":{"type":"number","exclusiveMinimum":0},"sinkAngleDeg":{"type":"number","exclusiveMinimum":0,"maximum":179.999}}}],"unevaluatedProperties":false};

function validate93(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate93.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.holeType === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "holeType"},message:"must have required property '"+"holeType"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.position === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "position"},message:"must have required property '"+"position"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.axis === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "axis"},message:"must have required property '"+"axis"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.diameter === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "diameter"},message:"must have required property '"+"diameter"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.sinkDiameter === undefined){
const err5 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sinkDiameter"},message:"must have required property '"+"sinkDiameter"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.sinkAngleDeg === undefined){
const err6 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sinkAngleDeg"},message:"must have required property '"+"sinkAngleDeg"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.operation !== undefined){
if("countersink" !== data.operation){
const err7 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "countersink"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.booleanMode !== undefined){
if("subtractive" !== data.booleanMode){
const err8 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/const",keyword:"const",params:{allowedValue: "subtractive"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.holeType !== undefined){
let data2 = data.holeType;
if(!((data2 === "through") || (data2 === "blind"))){
const err9 = {instancePath:instancePath+"/holeType",schemaPath:"#/allOf/1/properties/holeType/enum",keyword:"enum",params:{allowedValues: schema123.allOf[1].properties.holeType.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.position !== undefined){
let data3 = data.position;
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
if(data3.x === undefined){
const err10 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data3.y === undefined){
const err11 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(data3.z === undefined){
const err12 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
for(const key0 in data3){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err13 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data3.x !== undefined){
let data4 = data3.x;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err14 = {instancePath:instancePath+"/position/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data3.y !== undefined){
let data5 = data3.y;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err15 = {instancePath:instancePath+"/position/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data3.z !== undefined){
let data6 = data3.z;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err16 = {instancePath:instancePath+"/position/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath:instancePath+"/position",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.axis !== undefined){
let data7 = data.axis;
if(data7 && typeof data7 == "object" && !Array.isArray(data7)){
if(data7.x === undefined){
const err18 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data7.y === undefined){
const err19 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(data7.z === undefined){
const err20 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
for(const key1 in data7){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err21 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data7.x !== undefined){
let data8 = data7.x;
if(!((typeof data8 == "number") && (isFinite(data8)))){
const err22 = {instancePath:instancePath+"/axis/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data7.y !== undefined){
let data9 = data7.y;
if(!((typeof data9 == "number") && (isFinite(data9)))){
const err23 = {instancePath:instancePath+"/axis/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data7.z !== undefined){
let data10 = data7.z;
if(!((typeof data10 == "number") && (isFinite(data10)))){
const err24 = {instancePath:instancePath+"/axis/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
}
else {
const err25 = {instancePath:instancePath+"/axis",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.diameter !== undefined){
let data11 = data.diameter;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 <= 0 || isNaN(data11)){
const err26 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
else {
const err27 = {instancePath:instancePath+"/diameter",schemaPath:"#/allOf/1/properties/diameter/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.depth !== undefined){
let data12 = data.depth;
if((!((typeof data12 == "number") && (isFinite(data12)))) && (data12 !== null)){
const err28 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/type",keyword:"type",params:{type: schema123.allOf[1].properties.depth.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if((typeof data12 == "number") && (isFinite(data12))){
if(data12 <= 0 || isNaN(data12)){
const err29 = {instancePath:instancePath+"/depth",schemaPath:"#/allOf/1/properties/depth/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
}
if(data.sinkDiameter !== undefined){
let data13 = data.sinkDiameter;
if((typeof data13 == "number") && (isFinite(data13))){
if(data13 <= 0 || isNaN(data13)){
const err30 = {instancePath:instancePath+"/sinkDiameter",schemaPath:"#/allOf/1/properties/sinkDiameter/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
else {
const err31 = {instancePath:instancePath+"/sinkDiameter",schemaPath:"#/allOf/1/properties/sinkDiameter/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data.sinkAngleDeg !== undefined){
let data14 = data.sinkAngleDeg;
if((typeof data14 == "number") && (isFinite(data14))){
if(data14 > 179.999 || isNaN(data14)){
const err32 = {instancePath:instancePath+"/sinkAngleDeg",schemaPath:"#/allOf/1/properties/sinkAngleDeg/maximum",keyword:"maximum",params:{comparison: "<=", limit: 179.999},message:"must be <= 179.999"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(data14 <= 0 || isNaN(data14)){
const err33 = {instancePath:instancePath+"/sinkAngleDeg",schemaPath:"#/allOf/1/properties/sinkAngleDeg/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
else {
const err34 = {instancePath:instancePath+"/sinkAngleDeg",schemaPath:"#/allOf/1/properties/sinkAngleDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
}
else {
const err35 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key2 in data){
if(((((((((((((((((((key2 !== "operation") && (key2 !== "booleanMode")) && (key2 !== "holeType")) && (key2 !== "position")) && (key2 !== "axis")) && (key2 !== "diameter")) && (key2 !== "depth")) && (key2 !== "sinkDiameter")) && (key2 !== "sinkAngleDeg")) && (key2 !== "id")) && (key2 !== "name")) && (key2 !== "order")) && (key2 !== "dependencies")) && (key2 !== "suppressed")) && (key2 !== "sourceEvidence")) && (key2 !== "confidence")) && (key2 !== "userLocks")) && (key2 !== "overrides")) && (key2 !== "semanticOutputs")){
const err36 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key2},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
}
}
validate93.errors = vErrors;
return errors === 0;
}
validate93.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema126 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sketchId","profileIds","axis","angleDeg"],"properties":{"operation":{"const":"revolution"},"booleanMode":{"enum":["base","additive","subtractive"]},"sketchId":{"$ref":"#/$defs/identifier"},"profileIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"axis":{"$ref":"#/$defs/axis3"},"angleDeg":{"type":"number","exclusiveMinimum":0,"maximum":360}}}],"unevaluatedProperties":false};
const schema129 = {"type":"object","additionalProperties":false,"required":["origin","direction"],"properties":{"origin":{"$ref":"#/$defs/vector3"},"direction":{"$ref":"#/$defs/vector3"}}};

function validate98(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate98.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.origin === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "origin"},message:"must have required property '"+"origin"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.direction === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
for(const key0 in data){
if(!((key0 === "origin") || (key0 === "direction"))){
const err2 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.origin !== undefined){
let data0 = data.origin;
if(data0 && typeof data0 == "object" && !Array.isArray(data0)){
if(data0.x === undefined){
const err3 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data0.y === undefined){
const err4 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data0.z === undefined){
const err5 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key1 in data0){
if(!(((key1 === "x") || (key1 === "y")) || (key1 === "z"))){
const err6 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data0.x !== undefined){
let data1 = data0.x;
if(!((typeof data1 == "number") && (isFinite(data1)))){
const err7 = {instancePath:instancePath+"/origin/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data0.y !== undefined){
let data2 = data0.y;
if(!((typeof data2 == "number") && (isFinite(data2)))){
const err8 = {instancePath:instancePath+"/origin/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data0.z !== undefined){
let data3 = data0.z;
if(!((typeof data3 == "number") && (isFinite(data3)))){
const err9 = {instancePath:instancePath+"/origin/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
}
else {
const err10 = {instancePath:instancePath+"/origin",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.direction !== undefined){
let data4 = data.direction;
if(data4 && typeof data4 == "object" && !Array.isArray(data4)){
if(data4.x === undefined){
const err11 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(data4.y === undefined){
const err12 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data4.z === undefined){
const err13 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
for(const key2 in data4){
if(!(((key2 === "x") || (key2 === "y")) || (key2 === "z"))){
const err14 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data4.x !== undefined){
let data5 = data4.x;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err15 = {instancePath:instancePath+"/direction/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data4.y !== undefined){
let data6 = data4.y;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err16 = {instancePath:instancePath+"/direction/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data4.z !== undefined){
let data7 = data4.z;
if(!((typeof data7 == "number") && (isFinite(data7)))){
const err17 = {instancePath:instancePath+"/direction/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
else {
const err18 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
else {
const err19 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
validate98.errors = vErrors;
return errors === 0;
}
validate98.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate96(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate96.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sketchId === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sketchId"},message:"must have required property '"+"sketchId"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.profileIds === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "profileIds"},message:"must have required property '"+"profileIds"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.axis === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "axis"},message:"must have required property '"+"axis"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.angleDeg === undefined){
const err4 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "angleDeg"},message:"must have required property '"+"angleDeg"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.operation !== undefined){
if("revolution" !== data.operation){
const err5 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "revolution"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.booleanMode !== undefined){
let data1 = data.booleanMode;
if(!(((data1 === "base") || (data1 === "additive")) || (data1 === "subtractive"))){
const err6 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/enum",keyword:"enum",params:{allowedValues: schema126.allOf[1].properties.booleanMode.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.sketchId !== undefined){
let data2 = data.sketchId;
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err7 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(func2(data2) < 1){
const err8 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(!pattern4.test(data2)){
const err9 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/sketchId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.profileIds !== undefined){
let data3 = data.profileIds;
if(Array.isArray(data3)){
if(data3.length < 1){
const err11 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
const len0 = data3.length;
for(let i0=0; i0<len0; i0++){
let data4 = data3[i0];
if(typeof data4 === "string"){
if(func2(data4) > 160){
const err12 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(func2(data4) < 1){
const err13 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(!pattern4.test(data4)){
const err14 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/profileIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
let i1 = data3.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data3[i1], data3[j0])){
const err16 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err17 = {instancePath:instancePath+"/profileIds",schemaPath:"#/allOf/1/properties/profileIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.axis !== undefined){
if(!(validate98(data.axis, {instancePath:instancePath+"/axis",parentData:data,parentDataProperty:"axis",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate98.errors : vErrors.concat(validate98.errors);
errors = vErrors.length;
}
}
if(data.angleDeg !== undefined){
let data6 = data.angleDeg;
if((typeof data6 == "number") && (isFinite(data6))){
if(data6 > 360 || isNaN(data6)){
const err18 = {instancePath:instancePath+"/angleDeg",schemaPath:"#/allOf/1/properties/angleDeg/maximum",keyword:"maximum",params:{comparison: "<=", limit: 360},message:"must be <= 360"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(data6 <= 0 || isNaN(data6)){
const err19 = {instancePath:instancePath+"/angleDeg",schemaPath:"#/allOf/1/properties/angleDeg/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
else {
const err20 = {instancePath:instancePath+"/angleDeg",schemaPath:"#/allOf/1/properties/angleDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
}
else {
const err21 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if((((((((((((((((key0 !== "operation") && (key0 !== "booleanMode")) && (key0 !== "sketchId")) && (key0 !== "profileIds")) && (key0 !== "axis")) && (key0 !== "angleDeg")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err22 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
}
validate96.errors = vErrors;
return errors === 0;
}
validate96.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema132 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","direction","count","spacing"],"properties":{"operation":{"const":"linearPattern"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"direction":{"$ref":"#/$defs/vector3"},"count":{"type":"integer","minimum":2},"spacing":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false};

function validate101(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate101.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.sourceFeatureIds === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sourceFeatureIds"},message:"must have required property '"+"sourceFeatureIds"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.direction === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "direction"},message:"must have required property '"+"direction"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.count === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "count"},message:"must have required property '"+"count"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.spacing === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "spacing"},message:"must have required property '"+"spacing"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.operation !== undefined){
if("linearPattern" !== data.operation){
const err4 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "linearPattern"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.sourceFeatureIds !== undefined){
let data1 = data.sourceFeatureIds;
if(Array.isArray(data1)){
if(data1.length < 1){
const err5 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
const len0 = data1.length;
for(let i0=0; i0<len0; i0++){
let data2 = data1[i0];
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err6 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(func2(data2) < 1){
const err7 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(!pattern4.test(data2)){
const err8 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
else {
const err9 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
let i1 = data1.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data1[i1], data1[j0])){
const err10 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err11 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.direction !== undefined){
let data3 = data.direction;
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
if(data3.x === undefined){
const err12 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data3.y === undefined){
const err13 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data3.z === undefined){
const err14 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/required",keyword:"required",params:{missingProperty: "z"},message:"must have required property '"+"z"+"'"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
for(const key0 in data3){
if(!(((key0 === "x") || (key0 === "y")) || (key0 === "z"))){
const err15 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data3.x !== undefined){
let data4 = data3.x;
if(!((typeof data4 == "number") && (isFinite(data4)))){
const err16 = {instancePath:instancePath+"/direction/x",schemaPath:"#/$defs/vector3/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data3.y !== undefined){
let data5 = data3.y;
if(!((typeof data5 == "number") && (isFinite(data5)))){
const err17 = {instancePath:instancePath+"/direction/y",schemaPath:"#/$defs/vector3/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data3.z !== undefined){
let data6 = data3.z;
if(!((typeof data6 == "number") && (isFinite(data6)))){
const err18 = {instancePath:instancePath+"/direction/z",schemaPath:"#/$defs/vector3/properties/z/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
else {
const err19 = {instancePath:instancePath+"/direction",schemaPath:"#/$defs/vector3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data.count !== undefined){
let data7 = data.count;
if(!(((typeof data7 == "number") && (!(data7 % 1) && !isNaN(data7))) && (isFinite(data7)))){
const err20 = {instancePath:instancePath+"/count",schemaPath:"#/allOf/1/properties/count/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if((typeof data7 == "number") && (isFinite(data7))){
if(data7 < 2 || isNaN(data7)){
const err21 = {instancePath:instancePath+"/count",schemaPath:"#/allOf/1/properties/count/minimum",keyword:"minimum",params:{comparison: ">=", limit: 2},message:"must be >= 2"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
}
if(data.spacing !== undefined){
let data8 = data.spacing;
if((typeof data8 == "number") && (isFinite(data8))){
if(data8 <= 0 || isNaN(data8)){
const err22 = {instancePath:instancePath+"/spacing",schemaPath:"#/allOf/1/properties/spacing/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
else {
const err23 = {instancePath:instancePath+"/spacing",schemaPath:"#/allOf/1/properties/spacing/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
}
else {
const err24 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key1 in data){
if(((((((((((((((key1 !== "operation") && (key1 !== "sourceFeatureIds")) && (key1 !== "direction")) && (key1 !== "count")) && (key1 !== "spacing")) && (key1 !== "id")) && (key1 !== "name")) && (key1 !== "order")) && (key1 !== "dependencies")) && (key1 !== "suppressed")) && (key1 !== "sourceEvidence")) && (key1 !== "confidence")) && (key1 !== "userLocks")) && (key1 !== "overrides")) && (key1 !== "semanticOutputs")){
const err25 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key1},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
validate101.errors = vErrors;
return errors === 0;
}
validate101.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema135 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","axis","count","totalAngleDeg"],"properties":{"operation":{"const":"circularPattern"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"axis":{"$ref":"#/$defs/axis3"},"count":{"type":"integer","minimum":2},"totalAngleDeg":{"type":"number","exclusiveMinimum":0,"maximum":360}}}],"unevaluatedProperties":false};

function validate104(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate104.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.sourceFeatureIds === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sourceFeatureIds"},message:"must have required property '"+"sourceFeatureIds"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.axis === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "axis"},message:"must have required property '"+"axis"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.count === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "count"},message:"must have required property '"+"count"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.totalAngleDeg === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "totalAngleDeg"},message:"must have required property '"+"totalAngleDeg"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.operation !== undefined){
if("circularPattern" !== data.operation){
const err4 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "circularPattern"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.sourceFeatureIds !== undefined){
let data1 = data.sourceFeatureIds;
if(Array.isArray(data1)){
if(data1.length < 1){
const err5 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
const len0 = data1.length;
for(let i0=0; i0<len0; i0++){
let data2 = data1[i0];
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err6 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(func2(data2) < 1){
const err7 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(!pattern4.test(data2)){
const err8 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
else {
const err9 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
let i1 = data1.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data1[i1], data1[j0])){
const err10 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err11 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.axis !== undefined){
if(!(validate98(data.axis, {instancePath:instancePath+"/axis",parentData:data,parentDataProperty:"axis",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate98.errors : vErrors.concat(validate98.errors);
errors = vErrors.length;
}
}
if(data.count !== undefined){
let data4 = data.count;
if(!(((typeof data4 == "number") && (!(data4 % 1) && !isNaN(data4))) && (isFinite(data4)))){
const err12 = {instancePath:instancePath+"/count",schemaPath:"#/allOf/1/properties/count/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if((typeof data4 == "number") && (isFinite(data4))){
if(data4 < 2 || isNaN(data4)){
const err13 = {instancePath:instancePath+"/count",schemaPath:"#/allOf/1/properties/count/minimum",keyword:"minimum",params:{comparison: ">=", limit: 2},message:"must be >= 2"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
if(data.totalAngleDeg !== undefined){
let data5 = data.totalAngleDeg;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 > 360 || isNaN(data5)){
const err14 = {instancePath:instancePath+"/totalAngleDeg",schemaPath:"#/allOf/1/properties/totalAngleDeg/maximum",keyword:"maximum",params:{comparison: "<=", limit: 360},message:"must be <= 360"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(data5 <= 0 || isNaN(data5)){
const err15 = {instancePath:instancePath+"/totalAngleDeg",schemaPath:"#/allOf/1/properties/totalAngleDeg/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
else {
const err16 = {instancePath:instancePath+"/totalAngleDeg",schemaPath:"#/allOf/1/properties/totalAngleDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if(((((((((((((((key0 !== "operation") && (key0 !== "sourceFeatureIds")) && (key0 !== "axis")) && (key0 !== "count")) && (key0 !== "totalAngleDeg")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err18 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
}
validate104.errors = vErrors;
return errors === 0;
}
validate104.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema137 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["sourceFeatureIds","plane","keepOriginals"],"properties":{"operation":{"const":"mirror"},"sourceFeatureIds":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"plane":{"$ref":"#/$defs/plane3"},"keepOriginals":{"type":"boolean"}}}],"unevaluatedProperties":false};

function validate108(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate108.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.sourceFeatureIds === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sourceFeatureIds"},message:"must have required property '"+"sourceFeatureIds"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.plane === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "plane"},message:"must have required property '"+"plane"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.keepOriginals === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "keepOriginals"},message:"must have required property '"+"keepOriginals"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.operation !== undefined){
if("mirror" !== data.operation){
const err3 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "mirror"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.sourceFeatureIds !== undefined){
let data1 = data.sourceFeatureIds;
if(Array.isArray(data1)){
if(data1.length < 1){
const err4 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
const len0 = data1.length;
for(let i0=0; i0<len0; i0++){
let data2 = data1[i0];
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err5 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(func2(data2) < 1){
const err6 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(!pattern4.test(data2)){
const err7 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
else {
const err8 = {instancePath:instancePath+"/sourceFeatureIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
let i1 = data1.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data1[i1], data1[j0])){
const err9 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err10 = {instancePath:instancePath+"/sourceFeatureIds",schemaPath:"#/allOf/1/properties/sourceFeatureIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.plane !== undefined){
if(!(validate26(data.plane, {instancePath:instancePath+"/plane",parentData:data,parentDataProperty:"plane",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate26.errors : vErrors.concat(validate26.errors);
errors = vErrors.length;
}
}
if(data.keepOriginals !== undefined){
if(typeof data.keepOriginals !== "boolean"){
const err11 = {instancePath:instancePath+"/keepOriginals",schemaPath:"#/allOf/1/properties/keepOriginals/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if((((((((((((((key0 !== "operation") && (key0 !== "sourceFeatureIds")) && (key0 !== "plane")) && (key0 !== "keepOriginals")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err13 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
validate108.errors = vErrors;
return errors === 0;
}
validate108.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema139 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["targetEdges","width"],"properties":{"operation":{"const":"chamfer"},"targetEdges":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"width":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false};

function validate112(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate112.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.targetEdges === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "targetEdges"},message:"must have required property '"+"targetEdges"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.width === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.operation !== undefined){
if("chamfer" !== data.operation){
const err2 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "chamfer"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.targetEdges !== undefined){
let data1 = data.targetEdges;
if(Array.isArray(data1)){
if(data1.length < 1){
const err3 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
const len0 = data1.length;
for(let i0=0; i0<len0; i0++){
let data2 = data1[i0];
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err4 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(func2(data2) < 1){
const err5 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(!pattern4.test(data2)){
const err6 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
let i1 = data1.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data1[i1], data1[j0])){
const err8 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err9 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.width !== undefined){
let data3 = data.width;
if((typeof data3 == "number") && (isFinite(data3))){
if(data3 <= 0 || isNaN(data3)){
const err10 = {instancePath:instancePath+"/width",schemaPath:"#/allOf/1/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/width",schemaPath:"#/allOf/1/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if(((((((((((((key0 !== "operation") && (key0 !== "targetEdges")) && (key0 !== "width")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err13 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
validate112.errors = vErrors;
return errors === 0;
}
validate112.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema141 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["targetEdges","radius"],"properties":{"operation":{"const":"fillet"},"targetEdges":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"radius":{"type":"number","exclusiveMinimum":0}}}],"unevaluatedProperties":false};

function validate115(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate115.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.targetEdges === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "targetEdges"},message:"must have required property '"+"targetEdges"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.radius === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "radius"},message:"must have required property '"+"radius"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.operation !== undefined){
if("fillet" !== data.operation){
const err2 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "fillet"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
}
if(data.targetEdges !== undefined){
let data1 = data.targetEdges;
if(Array.isArray(data1)){
if(data1.length < 1){
const err3 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
const len0 = data1.length;
for(let i0=0; i0<len0; i0++){
let data2 = data1[i0];
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err4 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(func2(data2) < 1){
const err5 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(!pattern4.test(data2)){
const err6 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/targetEdges/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
let i1 = data1.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data1[i1], data1[j0])){
const err8 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err9 = {instancePath:instancePath+"/targetEdges",schemaPath:"#/allOf/1/properties/targetEdges/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.radius !== undefined){
let data3 = data.radius;
if((typeof data3 == "number") && (isFinite(data3))){
if(data3 <= 0 || isNaN(data3)){
const err10 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/radius",schemaPath:"#/allOf/1/properties/radius/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if(((((((((((((key0 !== "operation") && (key0 !== "targetEdges")) && (key0 !== "radius")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err13 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
validate115.errors = vErrors;
return errors === 0;
}
validate115.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema143 = {"allOf":[{"$ref":"#/$defs/featureBase"},{"type":"object","required":["booleanMode","sourceArtifactId","meshSha256","intent"],"properties":{"operation":{"const":"importedFaceted"},"booleanMode":{"enum":["base","additive","subtractive"]},"sourceArtifactId":{"$ref":"#/$defs/identifier"},"meshSha256":{"$ref":"#/$defs/sha256"},"intent":{"enum":["fallback","reference"]},"sewingTolerance":{"type":"number","exclusiveMinimum":0,"maximum":10,"description":"Explicit OCCT sewing tolerance in project units. The engine additionally enforces a physical maximum equivalent to 10 mm. Omit to require an already-watertight mesh."}}}],"unevaluatedProperties":false};

function validate118(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate118.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(!(validate75(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate75.errors : vErrors.concat(validate75.errors);
errors = vErrors.length;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.booleanMode === undefined){
const err0 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "booleanMode"},message:"must have required property '"+"booleanMode"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sourceArtifactId === undefined){
const err1 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "sourceArtifactId"},message:"must have required property '"+"sourceArtifactId"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.meshSha256 === undefined){
const err2 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "meshSha256"},message:"must have required property '"+"meshSha256"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.intent === undefined){
const err3 = {instancePath,schemaPath:"#/allOf/1/required",keyword:"required",params:{missingProperty: "intent"},message:"must have required property '"+"intent"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.operation !== undefined){
if("importedFaceted" !== data.operation){
const err4 = {instancePath:instancePath+"/operation",schemaPath:"#/allOf/1/properties/operation/const",keyword:"const",params:{allowedValue: "importedFaceted"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.booleanMode !== undefined){
let data1 = data.booleanMode;
if(!(((data1 === "base") || (data1 === "additive")) || (data1 === "subtractive"))){
const err5 = {instancePath:instancePath+"/booleanMode",schemaPath:"#/allOf/1/properties/booleanMode/enum",keyword:"enum",params:{allowedValues: schema143.allOf[1].properties.booleanMode.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.sourceArtifactId !== undefined){
let data2 = data.sourceArtifactId;
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err6 = {instancePath:instancePath+"/sourceArtifactId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(func2(data2) < 1){
const err7 = {instancePath:instancePath+"/sourceArtifactId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(!pattern4.test(data2)){
const err8 = {instancePath:instancePath+"/sourceArtifactId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
else {
const err9 = {instancePath:instancePath+"/sourceArtifactId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.meshSha256 !== undefined){
let data3 = data.meshSha256;
if(typeof data3 === "string"){
if(!pattern5.test(data3)){
const err10 = {instancePath:instancePath+"/meshSha256",schemaPath:"#/$defs/sha256/pattern",keyword:"pattern",params:{pattern: "^[a-f0-9]{64}$"},message:"must match pattern \""+"^[a-f0-9]{64}$"+"\""};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
else {
const err11 = {instancePath:instancePath+"/meshSha256",schemaPath:"#/$defs/sha256/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.intent !== undefined){
let data4 = data.intent;
if(!((data4 === "fallback") || (data4 === "reference"))){
const err12 = {instancePath:instancePath+"/intent",schemaPath:"#/allOf/1/properties/intent/enum",keyword:"enum",params:{allowedValues: schema143.allOf[1].properties.intent.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data.sewingTolerance !== undefined){
let data5 = data.sewingTolerance;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 > 10 || isNaN(data5)){
const err13 = {instancePath:instancePath+"/sewingTolerance",schemaPath:"#/allOf/1/properties/sewingTolerance/maximum",keyword:"maximum",params:{comparison: "<=", limit: 10},message:"must be <= 10"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data5 <= 0 || isNaN(data5)){
const err14 = {instancePath:instancePath+"/sewingTolerance",schemaPath:"#/allOf/1/properties/sewingTolerance/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/sewingTolerance",schemaPath:"#/allOf/1/properties/sewingTolerance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath,schemaPath:"#/allOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data && typeof data == "object" && !Array.isArray(data)){
for(const key0 in data){
if((((((((((((((((key0 !== "operation") && (key0 !== "booleanMode")) && (key0 !== "sourceArtifactId")) && (key0 !== "meshSha256")) && (key0 !== "intent")) && (key0 !== "sewingTolerance")) && (key0 !== "id")) && (key0 !== "name")) && (key0 !== "order")) && (key0 !== "dependencies")) && (key0 !== "suppressed")) && (key0 !== "sourceEvidence")) && (key0 !== "confidence")) && (key0 !== "userLocks")) && (key0 !== "overrides")) && (key0 !== "semanticOutputs")){
const err17 = {instancePath,schemaPath:"#/unevaluatedProperties",keyword:"unevaluatedProperties",params:{unevaluatedProperty: key0},message:"must NOT have unevaluated properties"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
validate118.errors = vErrors;
return errors === 0;
}
validate118.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate73(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate73.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
const _errs0 = errors;
let valid0 = false;
let passing0 = null;
const _errs1 = errors;
if(!(validate74(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate74.errors : vErrors.concat(validate74.errors);
errors = vErrors.length;
}
var _valid0 = _errs1 === errors;
if(_valid0){
valid0 = true;
passing0 = 0;
var props0 = true;
}
const _errs2 = errors;
if(!(validate82(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate82.errors : vErrors.concat(validate82.errors);
errors = vErrors.length;
}
var _valid0 = _errs2 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 1];
}
else {
if(_valid0){
valid0 = true;
passing0 = 1;
if(props0 !== true){
props0 = true;
}
}
const _errs3 = errors;
if(!(validate86(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate86.errors : vErrors.concat(validate86.errors);
errors = vErrors.length;
}
var _valid0 = _errs3 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 2];
}
else {
if(_valid0){
valid0 = true;
passing0 = 2;
if(props0 !== true){
props0 = true;
}
}
const _errs4 = errors;
if(!(validate90(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate90.errors : vErrors.concat(validate90.errors);
errors = vErrors.length;
}
var _valid0 = _errs4 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 3];
}
else {
if(_valid0){
valid0 = true;
passing0 = 3;
if(props0 !== true){
props0 = true;
}
}
const _errs5 = errors;
if(!(validate93(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate93.errors : vErrors.concat(validate93.errors);
errors = vErrors.length;
}
var _valid0 = _errs5 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 4];
}
else {
if(_valid0){
valid0 = true;
passing0 = 4;
if(props0 !== true){
props0 = true;
}
}
const _errs6 = errors;
if(!(validate96(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate96.errors : vErrors.concat(validate96.errors);
errors = vErrors.length;
}
var _valid0 = _errs6 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 5];
}
else {
if(_valid0){
valid0 = true;
passing0 = 5;
if(props0 !== true){
props0 = true;
}
}
const _errs7 = errors;
if(!(validate101(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate101.errors : vErrors.concat(validate101.errors);
errors = vErrors.length;
}
var _valid0 = _errs7 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 6];
}
else {
if(_valid0){
valid0 = true;
passing0 = 6;
if(props0 !== true){
props0 = true;
}
}
const _errs8 = errors;
if(!(validate104(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate104.errors : vErrors.concat(validate104.errors);
errors = vErrors.length;
}
var _valid0 = _errs8 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 7];
}
else {
if(_valid0){
valid0 = true;
passing0 = 7;
if(props0 !== true){
props0 = true;
}
}
const _errs9 = errors;
if(!(validate108(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate108.errors : vErrors.concat(validate108.errors);
errors = vErrors.length;
}
var _valid0 = _errs9 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 8];
}
else {
if(_valid0){
valid0 = true;
passing0 = 8;
if(props0 !== true){
props0 = true;
}
}
const _errs10 = errors;
if(!(validate112(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate112.errors : vErrors.concat(validate112.errors);
errors = vErrors.length;
}
var _valid0 = _errs10 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 9];
}
else {
if(_valid0){
valid0 = true;
passing0 = 9;
if(props0 !== true){
props0 = true;
}
}
const _errs11 = errors;
if(!(validate115(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate115.errors : vErrors.concat(validate115.errors);
errors = vErrors.length;
}
var _valid0 = _errs11 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 10];
}
else {
if(_valid0){
valid0 = true;
passing0 = 10;
if(props0 !== true){
props0 = true;
}
}
const _errs12 = errors;
if(!(validate118(data, {instancePath,parentData,parentDataProperty,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate118.errors : vErrors.concat(validate118.errors);
errors = vErrors.length;
}
var _valid0 = _errs12 === errors;
if(_valid0 && valid0){
valid0 = false;
passing0 = [passing0, 11];
}
else {
if(_valid0){
valid0 = true;
passing0 = 11;
if(props0 !== true){
props0 = true;
}
}
}
}
}
}
}
}
}
}
}
}
}
if(!valid0){
const err0 = {instancePath,schemaPath:"#/oneOf",keyword:"oneOf",params:{passingSchemas: passing0},message:"must match exactly one schema in oneOf"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
else {
errors = _errs0;
if(vErrors !== null){
if(_errs0){
vErrors.length = _errs0;
}
else {
vErrors = null;
}
}
}
validate73.errors = vErrors;
evaluated0.props = props0;
return errors === 0;
}
validate73.evaluated = {"dynamicProps":true,"dynamicItems":false};

const schema146 = {"type":"object","additionalProperties":false,"required":["id","kind","producerFeatureId","role","generatedFrom","status"],"properties":{"id":{"$ref":"#/$defs/identifier"},"kind":{"enum":["solid","shell","face","wire","edge","vertex","axis","plane"]},"producerFeatureId":{"$ref":"#/$defs/identifier"},"role":{"type":"string","minLength":1,"maxLength":200},"generatedFrom":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"status":{"enum":["resolved","unresolved"]},"kernelReference":{"type":["string","null"],"description":"Ephemeral diagnostic only; never the semantic identity."},"lastResolvedAt":{"$ref":"#/$defs/nullableTimestamp"}}};

function validate122(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate122.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.kind === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "kind"},message:"must have required property '"+"kind"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.producerFeatureId === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "producerFeatureId"},message:"must have required property '"+"producerFeatureId"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.role === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "role"},message:"must have required property '"+"role"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.generatedFrom === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "generatedFrom"},message:"must have required property '"+"generatedFrom"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.status === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "status"},message:"must have required property '"+"status"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
for(const key0 in data){
if(!((((((((key0 === "id") || (key0 === "kind")) || (key0 === "producerFeatureId")) || (key0 === "role")) || (key0 === "generatedFrom")) || (key0 === "status")) || (key0 === "kernelReference")) || (key0 === "lastResolvedAt"))){
const err6 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err7 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(func2(data0) < 1){
const err8 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(!pattern4.test(data0)){
const err9 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.kind !== undefined){
let data1 = data.kind;
if(!((((((((data1 === "solid") || (data1 === "shell")) || (data1 === "face")) || (data1 === "wire")) || (data1 === "edge")) || (data1 === "vertex")) || (data1 === "axis")) || (data1 === "plane"))){
const err11 = {instancePath:instancePath+"/kind",schemaPath:"#/properties/kind/enum",keyword:"enum",params:{allowedValues: schema146.properties.kind.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.producerFeatureId !== undefined){
let data2 = data.producerFeatureId;
if(typeof data2 === "string"){
if(func2(data2) > 160){
const err12 = {instancePath:instancePath+"/producerFeatureId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(func2(data2) < 1){
const err13 = {instancePath:instancePath+"/producerFeatureId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(!pattern4.test(data2)){
const err14 = {instancePath:instancePath+"/producerFeatureId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/producerFeatureId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.role !== undefined){
let data3 = data.role;
if(typeof data3 === "string"){
if(func2(data3) > 200){
const err16 = {instancePath:instancePath+"/role",schemaPath:"#/properties/role/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(func2(data3) < 1){
const err17 = {instancePath:instancePath+"/role",schemaPath:"#/properties/role/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
else {
const err18 = {instancePath:instancePath+"/role",schemaPath:"#/properties/role/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.generatedFrom !== undefined){
let data4 = data.generatedFrom;
if(Array.isArray(data4)){
const len0 = data4.length;
for(let i0=0; i0<len0; i0++){
let data5 = data4[i0];
if(typeof data5 === "string"){
if(func2(data5) > 160){
const err19 = {instancePath:instancePath+"/generatedFrom/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
if(func2(data5) < 1){
const err20 = {instancePath:instancePath+"/generatedFrom/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if(!pattern4.test(data5)){
const err21 = {instancePath:instancePath+"/generatedFrom/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
else {
const err22 = {instancePath:instancePath+"/generatedFrom/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
let i1 = data4.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data4[i1], data4[j0])){
const err23 = {instancePath:instancePath+"/generatedFrom",schemaPath:"#/properties/generatedFrom/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err24 = {instancePath:instancePath+"/generatedFrom",schemaPath:"#/properties/generatedFrom/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data.status !== undefined){
let data6 = data.status;
if(!((data6 === "resolved") || (data6 === "unresolved"))){
const err25 = {instancePath:instancePath+"/status",schemaPath:"#/properties/status/enum",keyword:"enum",params:{allowedValues: schema146.properties.status.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
if(data.kernelReference !== undefined){
let data7 = data.kernelReference;
if((typeof data7 !== "string") && (data7 !== null)){
const err26 = {instancePath:instancePath+"/kernelReference",schemaPath:"#/properties/kernelReference/type",keyword:"type",params:{type: schema146.properties.kernelReference.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.lastResolvedAt !== undefined){
let data8 = data.lastResolvedAt;
if((typeof data8 !== "string") && (data8 !== null)){
const err27 = {instancePath:instancePath+"/lastResolvedAt",schemaPath:"#/$defs/nullableTimestamp/type",keyword:"type",params:{type: schema95.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
if(typeof data8 === "string"){
if(!(formats0.validate(data8))){
const err28 = {instancePath:instancePath+"/lastResolvedAt",schemaPath:"#/$defs/nullableTimestamp/format",keyword:"format",params:{format: "date-time"},message:"must match format \""+"date-time"+"\""};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
}
}
else {
const err29 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
validate122.errors = vErrors;
return errors === 0;
}
validate122.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema151 = {"type":"object","additionalProperties":false,"required":["id","sourceType","sourceIds","confidence"],"properties":{"id":{"$ref":"#/$defs/identifier"},"sourceType":{"enum":["meshPatch","meshTriangle","sketchEntity","feature","user","engine","imported","derived"]},"sourceIds":{"type":"array","items":{"$ref":"#/$defs/identifier"},"uniqueItems":true},"measuredValue":{"type":["number","null"]},"suggestedNominalValue":{"type":["number","null"]},"residual":{"type":["number","null"],"minimum":0},"confidence":{"$ref":"#/$defs/confidence"},"notes":{"type":["string","null"],"maxLength":2000},"metadata":{"type":["object","null"],"additionalProperties":{"$ref":"#/$defs/jsonValue"}}}};

function validate124(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate124.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.id === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.sourceType === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceType"},message:"must have required property '"+"sourceType"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.sourceIds === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceIds"},message:"must have required property '"+"sourceIds"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.confidence === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "confidence"},message:"must have required property '"+"confidence"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema151.properties, key0))){
const err4 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.id !== undefined){
let data0 = data.id;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err5 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(func2(data0) < 1){
const err6 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(!pattern4.test(data0)){
const err7 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
else {
const err8 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.sourceType !== undefined){
let data1 = data.sourceType;
if(!((((((((data1 === "meshPatch") || (data1 === "meshTriangle")) || (data1 === "sketchEntity")) || (data1 === "feature")) || (data1 === "user")) || (data1 === "engine")) || (data1 === "imported")) || (data1 === "derived"))){
const err9 = {instancePath:instancePath+"/sourceType",schemaPath:"#/properties/sourceType/enum",keyword:"enum",params:{allowedValues: schema151.properties.sourceType.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.sourceIds !== undefined){
let data2 = data.sourceIds;
if(Array.isArray(data2)){
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
let data3 = data2[i0];
if(typeof data3 === "string"){
if(func2(data3) > 160){
const err10 = {instancePath:instancePath+"/sourceIds/" + i0,schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(func2(data3) < 1){
const err11 = {instancePath:instancePath+"/sourceIds/" + i0,schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(!pattern4.test(data3)){
const err12 = {instancePath:instancePath+"/sourceIds/" + i0,schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
else {
const err13 = {instancePath:instancePath+"/sourceIds/" + i0,schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
let i1 = data2.length;
let j0;
if(i1 > 1){
outer0:
for(;i1--;){
for(j0 = i1; j0--;){
if(func0(data2[i1], data2[j0])){
const err14 = {instancePath:instancePath+"/sourceIds",schemaPath:"#/properties/sourceIds/uniqueItems",keyword:"uniqueItems",params:{i: i1, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i1+" are identical)"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
break outer0;
}
}
}
}
}
else {
const err15 = {instancePath:instancePath+"/sourceIds",schemaPath:"#/properties/sourceIds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data.measuredValue !== undefined){
let data4 = data.measuredValue;
if((!((typeof data4 == "number") && (isFinite(data4)))) && (data4 !== null)){
const err16 = {instancePath:instancePath+"/measuredValue",schemaPath:"#/properties/measuredValue/type",keyword:"type",params:{type: schema151.properties.measuredValue.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data.suggestedNominalValue !== undefined){
let data5 = data.suggestedNominalValue;
if((!((typeof data5 == "number") && (isFinite(data5)))) && (data5 !== null)){
const err17 = {instancePath:instancePath+"/suggestedNominalValue",schemaPath:"#/properties/suggestedNominalValue/type",keyword:"type",params:{type: schema151.properties.suggestedNominalValue.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.residual !== undefined){
let data6 = data.residual;
if((!((typeof data6 == "number") && (isFinite(data6)))) && (data6 !== null)){
const err18 = {instancePath:instancePath+"/residual",schemaPath:"#/properties/residual/type",keyword:"type",params:{type: schema151.properties.residual.type},message:"must be number,null"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if((typeof data6 == "number") && (isFinite(data6))){
if(data6 < 0 || isNaN(data6)){
const err19 = {instancePath:instancePath+"/residual",schemaPath:"#/properties/residual/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
if(data.confidence !== undefined){
let data7 = data.confidence;
if((typeof data7 == "number") && (isFinite(data7))){
if(data7 > 1 || isNaN(data7)){
const err20 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if(data7 < 0 || isNaN(data7)){
const err21 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
else {
const err22 = {instancePath:instancePath+"/confidence",schemaPath:"#/$defs/confidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data.notes !== undefined){
let data8 = data.notes;
if((typeof data8 !== "string") && (data8 !== null)){
const err23 = {instancePath:instancePath+"/notes",schemaPath:"#/properties/notes/type",keyword:"type",params:{type: schema151.properties.notes.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
if(typeof data8 === "string"){
if(func2(data8) > 2000){
const err24 = {instancePath:instancePath+"/notes",schemaPath:"#/properties/notes/maxLength",keyword:"maxLength",params:{limit: 2000},message:"must NOT have more than 2000 characters"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
}
if(data.metadata !== undefined){
let data9 = data.metadata;
if((!(data9 && typeof data9 == "object" && !Array.isArray(data9))) && (data9 !== null)){
const err25 = {instancePath:instancePath+"/metadata",schemaPath:"#/properties/metadata/type",keyword:"type",params:{type: schema151.properties.metadata.type},message:"must be object,null"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
if(data9 && typeof data9 == "object" && !Array.isArray(data9)){
for(const key1 in data9){
if(!(validate68(data9[key1], {instancePath:instancePath+"/metadata/" + key1.replace(/~/g, "~0").replace(/\//g, "~1"),parentData:data9,parentDataProperty:key1,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate68.errors : vErrors.concat(validate68.errors);
errors = vErrors.length;
}
}
}
}
}
else {
const err26 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
validate124.errors = vErrors;
return errors === 0;
}
validate124.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema155 = {"type":"object","additionalProperties":false,"required":["maxFeatures","beamWidth","candidatesPerResidual","wallClockSeconds","maxRebuilds","minScoreImprovement","nominalSnappingEnabled","nominalSnapTolerance","scoreWeights"],"properties":{"maxFeatures":{"type":"integer","minimum":1},"beamWidth":{"type":"integer","minimum":1},"candidatesPerResidual":{"type":"integer","minimum":1},"wallClockSeconds":{"type":"number","exclusiveMinimum":0},"maxRebuilds":{"type":"integer","minimum":1},"minScoreImprovement":{"type":"number","minimum":0},"nominalSnappingEnabled":{"type":"boolean"},"nominalSnapTolerance":{"type":"number","minimum":0},"scoreWeights":{"$ref":"#/$defs/scoreWeights"}}};
const schema156 = {"type":"object","additionalProperties":false,"required":["rmsDistance","p95Distance","maxDistance","normalAgreement","volumeDifference","overlap","sharpEdgeAlignment","boundaryAlignment","unmatchedSource","excessResult","complexity","unsupportedOperation","evidenceConfidence"],"properties":{"rmsDistance":{"type":"number","minimum":0},"p95Distance":{"type":"number","minimum":0},"maxDistance":{"type":"number","minimum":0},"normalAgreement":{"type":"number","minimum":0},"volumeDifference":{"type":"number","minimum":0},"overlap":{"type":"number","minimum":0},"sharpEdgeAlignment":{"type":"number","minimum":0},"boundaryAlignment":{"type":"number","minimum":0},"unmatchedSource":{"type":"number","minimum":0},"excessResult":{"type":"number","minimum":0},"complexity":{"type":"number","minimum":0},"unsupportedOperation":{"type":"number","minimum":0},"evidenceConfidence":{"type":"number","minimum":0}}};

function validate129(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate129.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.maxFeatures === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "maxFeatures"},message:"must have required property '"+"maxFeatures"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.beamWidth === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "beamWidth"},message:"must have required property '"+"beamWidth"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.candidatesPerResidual === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "candidatesPerResidual"},message:"must have required property '"+"candidatesPerResidual"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.wallClockSeconds === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "wallClockSeconds"},message:"must have required property '"+"wallClockSeconds"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.maxRebuilds === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "maxRebuilds"},message:"must have required property '"+"maxRebuilds"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.minScoreImprovement === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "minScoreImprovement"},message:"must have required property '"+"minScoreImprovement"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.nominalSnappingEnabled === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "nominalSnappingEnabled"},message:"must have required property '"+"nominalSnappingEnabled"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.nominalSnapTolerance === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "nominalSnapTolerance"},message:"must have required property '"+"nominalSnapTolerance"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data.scoreWeights === undefined){
const err8 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "scoreWeights"},message:"must have required property '"+"scoreWeights"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema155.properties, key0))){
const err9 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.maxFeatures !== undefined){
let data0 = data.maxFeatures;
if(!(((typeof data0 == "number") && (!(data0 % 1) && !isNaN(data0))) && (isFinite(data0)))){
const err10 = {instancePath:instancePath+"/maxFeatures",schemaPath:"#/properties/maxFeatures/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if((typeof data0 == "number") && (isFinite(data0))){
if(data0 < 1 || isNaN(data0)){
const err11 = {instancePath:instancePath+"/maxFeatures",schemaPath:"#/properties/maxFeatures/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
if(data.beamWidth !== undefined){
let data1 = data.beamWidth;
if(!(((typeof data1 == "number") && (!(data1 % 1) && !isNaN(data1))) && (isFinite(data1)))){
const err12 = {instancePath:instancePath+"/beamWidth",schemaPath:"#/properties/beamWidth/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if((typeof data1 == "number") && (isFinite(data1))){
if(data1 < 1 || isNaN(data1)){
const err13 = {instancePath:instancePath+"/beamWidth",schemaPath:"#/properties/beamWidth/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
}
if(data.candidatesPerResidual !== undefined){
let data2 = data.candidatesPerResidual;
if(!(((typeof data2 == "number") && (!(data2 % 1) && !isNaN(data2))) && (isFinite(data2)))){
const err14 = {instancePath:instancePath+"/candidatesPerResidual",schemaPath:"#/properties/candidatesPerResidual/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if((typeof data2 == "number") && (isFinite(data2))){
if(data2 < 1 || isNaN(data2)){
const err15 = {instancePath:instancePath+"/candidatesPerResidual",schemaPath:"#/properties/candidatesPerResidual/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
if(data.wallClockSeconds !== undefined){
let data3 = data.wallClockSeconds;
if((typeof data3 == "number") && (isFinite(data3))){
if(data3 <= 0 || isNaN(data3)){
const err16 = {instancePath:instancePath+"/wallClockSeconds",schemaPath:"#/properties/wallClockSeconds/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
else {
const err17 = {instancePath:instancePath+"/wallClockSeconds",schemaPath:"#/properties/wallClockSeconds/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data.maxRebuilds !== undefined){
let data4 = data.maxRebuilds;
if(!(((typeof data4 == "number") && (!(data4 % 1) && !isNaN(data4))) && (isFinite(data4)))){
const err18 = {instancePath:instancePath+"/maxRebuilds",schemaPath:"#/properties/maxRebuilds/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if((typeof data4 == "number") && (isFinite(data4))){
if(data4 < 1 || isNaN(data4)){
const err19 = {instancePath:instancePath+"/maxRebuilds",schemaPath:"#/properties/maxRebuilds/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
if(data.minScoreImprovement !== undefined){
let data5 = data.minScoreImprovement;
if((typeof data5 == "number") && (isFinite(data5))){
if(data5 < 0 || isNaN(data5)){
const err20 = {instancePath:instancePath+"/minScoreImprovement",schemaPath:"#/properties/minScoreImprovement/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
else {
const err21 = {instancePath:instancePath+"/minScoreImprovement",schemaPath:"#/properties/minScoreImprovement/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data.nominalSnappingEnabled !== undefined){
if(typeof data.nominalSnappingEnabled !== "boolean"){
const err22 = {instancePath:instancePath+"/nominalSnappingEnabled",schemaPath:"#/properties/nominalSnappingEnabled/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data.nominalSnapTolerance !== undefined){
let data7 = data.nominalSnapTolerance;
if((typeof data7 == "number") && (isFinite(data7))){
if(data7 < 0 || isNaN(data7)){
const err23 = {instancePath:instancePath+"/nominalSnapTolerance",schemaPath:"#/properties/nominalSnapTolerance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
else {
const err24 = {instancePath:instancePath+"/nominalSnapTolerance",schemaPath:"#/properties/nominalSnapTolerance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
}
if(data.scoreWeights !== undefined){
let data8 = data.scoreWeights;
if(data8 && typeof data8 == "object" && !Array.isArray(data8)){
if(data8.rmsDistance === undefined){
const err25 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "rmsDistance"},message:"must have required property '"+"rmsDistance"+"'"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
if(data8.p95Distance === undefined){
const err26 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "p95Distance"},message:"must have required property '"+"p95Distance"+"'"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
if(data8.maxDistance === undefined){
const err27 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "maxDistance"},message:"must have required property '"+"maxDistance"+"'"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
if(data8.normalAgreement === undefined){
const err28 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "normalAgreement"},message:"must have required property '"+"normalAgreement"+"'"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if(data8.volumeDifference === undefined){
const err29 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "volumeDifference"},message:"must have required property '"+"volumeDifference"+"'"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
if(data8.overlap === undefined){
const err30 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "overlap"},message:"must have required property '"+"overlap"+"'"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
if(data8.sharpEdgeAlignment === undefined){
const err31 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "sharpEdgeAlignment"},message:"must have required property '"+"sharpEdgeAlignment"+"'"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
if(data8.boundaryAlignment === undefined){
const err32 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "boundaryAlignment"},message:"must have required property '"+"boundaryAlignment"+"'"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(data8.unmatchedSource === undefined){
const err33 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "unmatchedSource"},message:"must have required property '"+"unmatchedSource"+"'"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
if(data8.excessResult === undefined){
const err34 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "excessResult"},message:"must have required property '"+"excessResult"+"'"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
if(data8.complexity === undefined){
const err35 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "complexity"},message:"must have required property '"+"complexity"+"'"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
if(data8.unsupportedOperation === undefined){
const err36 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "unsupportedOperation"},message:"must have required property '"+"unsupportedOperation"+"'"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
if(data8.evidenceConfidence === undefined){
const err37 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/required",keyword:"required",params:{missingProperty: "evidenceConfidence"},message:"must have required property '"+"evidenceConfidence"+"'"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
for(const key1 in data8){
if(!(func1.call(schema156.properties, key1))){
const err38 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
if(data8.rmsDistance !== undefined){
let data9 = data8.rmsDistance;
if((typeof data9 == "number") && (isFinite(data9))){
if(data9 < 0 || isNaN(data9)){
const err39 = {instancePath:instancePath+"/scoreWeights/rmsDistance",schemaPath:"#/$defs/scoreWeights/properties/rmsDistance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
else {
const err40 = {instancePath:instancePath+"/scoreWeights/rmsDistance",schemaPath:"#/$defs/scoreWeights/properties/rmsDistance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
if(data8.p95Distance !== undefined){
let data10 = data8.p95Distance;
if((typeof data10 == "number") && (isFinite(data10))){
if(data10 < 0 || isNaN(data10)){
const err41 = {instancePath:instancePath+"/scoreWeights/p95Distance",schemaPath:"#/$defs/scoreWeights/properties/p95Distance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
}
else {
const err42 = {instancePath:instancePath+"/scoreWeights/p95Distance",schemaPath:"#/$defs/scoreWeights/properties/p95Distance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
}
if(data8.maxDistance !== undefined){
let data11 = data8.maxDistance;
if((typeof data11 == "number") && (isFinite(data11))){
if(data11 < 0 || isNaN(data11)){
const err43 = {instancePath:instancePath+"/scoreWeights/maxDistance",schemaPath:"#/$defs/scoreWeights/properties/maxDistance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
}
}
else {
const err44 = {instancePath:instancePath+"/scoreWeights/maxDistance",schemaPath:"#/$defs/scoreWeights/properties/maxDistance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
}
if(data8.normalAgreement !== undefined){
let data12 = data8.normalAgreement;
if((typeof data12 == "number") && (isFinite(data12))){
if(data12 < 0 || isNaN(data12)){
const err45 = {instancePath:instancePath+"/scoreWeights/normalAgreement",schemaPath:"#/$defs/scoreWeights/properties/normalAgreement/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
}
else {
const err46 = {instancePath:instancePath+"/scoreWeights/normalAgreement",schemaPath:"#/$defs/scoreWeights/properties/normalAgreement/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err46];
}
else {
vErrors.push(err46);
}
errors++;
}
}
if(data8.volumeDifference !== undefined){
let data13 = data8.volumeDifference;
if((typeof data13 == "number") && (isFinite(data13))){
if(data13 < 0 || isNaN(data13)){
const err47 = {instancePath:instancePath+"/scoreWeights/volumeDifference",schemaPath:"#/$defs/scoreWeights/properties/volumeDifference/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err47];
}
else {
vErrors.push(err47);
}
errors++;
}
}
else {
const err48 = {instancePath:instancePath+"/scoreWeights/volumeDifference",schemaPath:"#/$defs/scoreWeights/properties/volumeDifference/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err48];
}
else {
vErrors.push(err48);
}
errors++;
}
}
if(data8.overlap !== undefined){
let data14 = data8.overlap;
if((typeof data14 == "number") && (isFinite(data14))){
if(data14 < 0 || isNaN(data14)){
const err49 = {instancePath:instancePath+"/scoreWeights/overlap",schemaPath:"#/$defs/scoreWeights/properties/overlap/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err49];
}
else {
vErrors.push(err49);
}
errors++;
}
}
else {
const err50 = {instancePath:instancePath+"/scoreWeights/overlap",schemaPath:"#/$defs/scoreWeights/properties/overlap/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err50];
}
else {
vErrors.push(err50);
}
errors++;
}
}
if(data8.sharpEdgeAlignment !== undefined){
let data15 = data8.sharpEdgeAlignment;
if((typeof data15 == "number") && (isFinite(data15))){
if(data15 < 0 || isNaN(data15)){
const err51 = {instancePath:instancePath+"/scoreWeights/sharpEdgeAlignment",schemaPath:"#/$defs/scoreWeights/properties/sharpEdgeAlignment/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err51];
}
else {
vErrors.push(err51);
}
errors++;
}
}
else {
const err52 = {instancePath:instancePath+"/scoreWeights/sharpEdgeAlignment",schemaPath:"#/$defs/scoreWeights/properties/sharpEdgeAlignment/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err52];
}
else {
vErrors.push(err52);
}
errors++;
}
}
if(data8.boundaryAlignment !== undefined){
let data16 = data8.boundaryAlignment;
if((typeof data16 == "number") && (isFinite(data16))){
if(data16 < 0 || isNaN(data16)){
const err53 = {instancePath:instancePath+"/scoreWeights/boundaryAlignment",schemaPath:"#/$defs/scoreWeights/properties/boundaryAlignment/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err53];
}
else {
vErrors.push(err53);
}
errors++;
}
}
else {
const err54 = {instancePath:instancePath+"/scoreWeights/boundaryAlignment",schemaPath:"#/$defs/scoreWeights/properties/boundaryAlignment/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err54];
}
else {
vErrors.push(err54);
}
errors++;
}
}
if(data8.unmatchedSource !== undefined){
let data17 = data8.unmatchedSource;
if((typeof data17 == "number") && (isFinite(data17))){
if(data17 < 0 || isNaN(data17)){
const err55 = {instancePath:instancePath+"/scoreWeights/unmatchedSource",schemaPath:"#/$defs/scoreWeights/properties/unmatchedSource/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err55];
}
else {
vErrors.push(err55);
}
errors++;
}
}
else {
const err56 = {instancePath:instancePath+"/scoreWeights/unmatchedSource",schemaPath:"#/$defs/scoreWeights/properties/unmatchedSource/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err56];
}
else {
vErrors.push(err56);
}
errors++;
}
}
if(data8.excessResult !== undefined){
let data18 = data8.excessResult;
if((typeof data18 == "number") && (isFinite(data18))){
if(data18 < 0 || isNaN(data18)){
const err57 = {instancePath:instancePath+"/scoreWeights/excessResult",schemaPath:"#/$defs/scoreWeights/properties/excessResult/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err57];
}
else {
vErrors.push(err57);
}
errors++;
}
}
else {
const err58 = {instancePath:instancePath+"/scoreWeights/excessResult",schemaPath:"#/$defs/scoreWeights/properties/excessResult/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err58];
}
else {
vErrors.push(err58);
}
errors++;
}
}
if(data8.complexity !== undefined){
let data19 = data8.complexity;
if((typeof data19 == "number") && (isFinite(data19))){
if(data19 < 0 || isNaN(data19)){
const err59 = {instancePath:instancePath+"/scoreWeights/complexity",schemaPath:"#/$defs/scoreWeights/properties/complexity/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err59];
}
else {
vErrors.push(err59);
}
errors++;
}
}
else {
const err60 = {instancePath:instancePath+"/scoreWeights/complexity",schemaPath:"#/$defs/scoreWeights/properties/complexity/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err60];
}
else {
vErrors.push(err60);
}
errors++;
}
}
if(data8.unsupportedOperation !== undefined){
let data20 = data8.unsupportedOperation;
if((typeof data20 == "number") && (isFinite(data20))){
if(data20 < 0 || isNaN(data20)){
const err61 = {instancePath:instancePath+"/scoreWeights/unsupportedOperation",schemaPath:"#/$defs/scoreWeights/properties/unsupportedOperation/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err61];
}
else {
vErrors.push(err61);
}
errors++;
}
}
else {
const err62 = {instancePath:instancePath+"/scoreWeights/unsupportedOperation",schemaPath:"#/$defs/scoreWeights/properties/unsupportedOperation/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err62];
}
else {
vErrors.push(err62);
}
errors++;
}
}
if(data8.evidenceConfidence !== undefined){
let data21 = data8.evidenceConfidence;
if((typeof data21 == "number") && (isFinite(data21))){
if(data21 < 0 || isNaN(data21)){
const err63 = {instancePath:instancePath+"/scoreWeights/evidenceConfidence",schemaPath:"#/$defs/scoreWeights/properties/evidenceConfidence/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err63];
}
else {
vErrors.push(err63);
}
errors++;
}
}
else {
const err64 = {instancePath:instancePath+"/scoreWeights/evidenceConfidence",schemaPath:"#/$defs/scoreWeights/properties/evidenceConfidence/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err64];
}
else {
vErrors.push(err64);
}
errors++;
}
}
}
else {
const err65 = {instancePath:instancePath+"/scoreWeights",schemaPath:"#/$defs/scoreWeights/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err65];
}
else {
vErrors.push(err65);
}
errors++;
}
}
}
else {
const err66 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err66];
}
else {
vErrors.push(err66);
}
errors++;
}
validate129.errors = vErrors;
return errors === 0;
}
validate129.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema159 = {"type":"object","additionalProperties":false,"required":["status","brepValid","stepReimportValid","toleranceSatisfied","issues"],"properties":{"status":{"enum":["notRun","pending","valid","invalid","partial"]},"brepValid":{"type":["boolean","null"]},"stepReimportValid":{"type":["boolean","null"]},"toleranceSatisfied":{"type":["boolean","null"]},"checkedAt":{"$ref":"#/$defs/nullableTimestamp"},"lastValidFeatureId":{"$ref":"#/$defs/nullableIdentifier"},"issues":{"type":"array","items":{"$ref":"#/$defs/validationIssue"}}}};
const schema161 = {"type":"object","additionalProperties":false,"required":["code","message","severity"],"properties":{"code":{"type":"string","minLength":1},"message":{"type":"string","minLength":1},"severity":{"enum":["info","warning","error"]},"featureId":{"$ref":"#/$defs/nullableIdentifier"},"semanticReference":{"$ref":"#/$defs/nullableIdentifier"},"details":{"type":["object","null"],"additionalProperties":{"$ref":"#/$defs/jsonValue"}}}};

function validate133(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate133.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.code === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "code"},message:"must have required property '"+"code"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.message === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "message"},message:"must have required property '"+"message"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.severity === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "severity"},message:"must have required property '"+"severity"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
for(const key0 in data){
if(!((((((key0 === "code") || (key0 === "message")) || (key0 === "severity")) || (key0 === "featureId")) || (key0 === "semanticReference")) || (key0 === "details"))){
const err3 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
if(data.code !== undefined){
let data0 = data.code;
if(typeof data0 === "string"){
if(func2(data0) < 1){
const err4 = {instancePath:instancePath+"/code",schemaPath:"#/properties/code/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
else {
const err5 = {instancePath:instancePath+"/code",schemaPath:"#/properties/code/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.message !== undefined){
let data1 = data.message;
if(typeof data1 === "string"){
if(func2(data1) < 1){
const err6 = {instancePath:instancePath+"/message",schemaPath:"#/properties/message/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
else {
const err7 = {instancePath:instancePath+"/message",schemaPath:"#/properties/message/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.severity !== undefined){
let data2 = data.severity;
if(!(((data2 === "info") || (data2 === "warning")) || (data2 === "error"))){
const err8 = {instancePath:instancePath+"/severity",schemaPath:"#/properties/severity/enum",keyword:"enum",params:{allowedValues: schema161.properties.severity.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.featureId !== undefined){
if(!(validate79(data.featureId, {instancePath:instancePath+"/featureId",parentData:data,parentDataProperty:"featureId",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
if(data.semanticReference !== undefined){
if(!(validate79(data.semanticReference, {instancePath:instancePath+"/semanticReference",parentData:data,parentDataProperty:"semanticReference",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
if(data.details !== undefined){
let data5 = data.details;
if((!(data5 && typeof data5 == "object" && !Array.isArray(data5))) && (data5 !== null)){
const err9 = {instancePath:instancePath+"/details",schemaPath:"#/properties/details/type",keyword:"type",params:{type: schema161.properties.details.type},message:"must be object,null"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
for(const key1 in data5){
if(!(validate68(data5[key1], {instancePath:instancePath+"/details/" + key1.replace(/~/g, "~0").replace(/\//g, "~1"),parentData:data5,parentDataProperty:key1,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate68.errors : vErrors.concat(validate68.errors);
errors = vErrors.length;
}
}
}
}
}
else {
const err10 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
validate133.errors = vErrors;
return errors === 0;
}
validate133.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate131(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate131.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.status === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "status"},message:"must have required property '"+"status"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.brepValid === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "brepValid"},message:"must have required property '"+"brepValid"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.stepReimportValid === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "stepReimportValid"},message:"must have required property '"+"stepReimportValid"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.toleranceSatisfied === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "toleranceSatisfied"},message:"must have required property '"+"toleranceSatisfied"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.issues === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "issues"},message:"must have required property '"+"issues"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
for(const key0 in data){
if(!(((((((key0 === "status") || (key0 === "brepValid")) || (key0 === "stepReimportValid")) || (key0 === "toleranceSatisfied")) || (key0 === "checkedAt")) || (key0 === "lastValidFeatureId")) || (key0 === "issues"))){
const err5 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.status !== undefined){
let data0 = data.status;
if(!(((((data0 === "notRun") || (data0 === "pending")) || (data0 === "valid")) || (data0 === "invalid")) || (data0 === "partial"))){
const err6 = {instancePath:instancePath+"/status",schemaPath:"#/properties/status/enum",keyword:"enum",params:{allowedValues: schema159.properties.status.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.brepValid !== undefined){
let data1 = data.brepValid;
if((typeof data1 !== "boolean") && (data1 !== null)){
const err7 = {instancePath:instancePath+"/brepValid",schemaPath:"#/properties/brepValid/type",keyword:"type",params:{type: schema159.properties.brepValid.type},message:"must be boolean,null"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.stepReimportValid !== undefined){
let data2 = data.stepReimportValid;
if((typeof data2 !== "boolean") && (data2 !== null)){
const err8 = {instancePath:instancePath+"/stepReimportValid",schemaPath:"#/properties/stepReimportValid/type",keyword:"type",params:{type: schema159.properties.stepReimportValid.type},message:"must be boolean,null"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.toleranceSatisfied !== undefined){
let data3 = data.toleranceSatisfied;
if((typeof data3 !== "boolean") && (data3 !== null)){
const err9 = {instancePath:instancePath+"/toleranceSatisfied",schemaPath:"#/properties/toleranceSatisfied/type",keyword:"type",params:{type: schema159.properties.toleranceSatisfied.type},message:"must be boolean,null"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.checkedAt !== undefined){
let data4 = data.checkedAt;
if((typeof data4 !== "string") && (data4 !== null)){
const err10 = {instancePath:instancePath+"/checkedAt",schemaPath:"#/$defs/nullableTimestamp/type",keyword:"type",params:{type: schema95.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(typeof data4 === "string"){
if(!(formats0.validate(data4))){
const err11 = {instancePath:instancePath+"/checkedAt",schemaPath:"#/$defs/nullableTimestamp/format",keyword:"format",params:{format: "date-time"},message:"must match format \""+"date-time"+"\""};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
if(data.lastValidFeatureId !== undefined){
if(!(validate79(data.lastValidFeatureId, {instancePath:instancePath+"/lastValidFeatureId",parentData:data,parentDataProperty:"lastValidFeatureId",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
if(data.issues !== undefined){
let data6 = data.issues;
if(Array.isArray(data6)){
const len0 = data6.length;
for(let i0=0; i0<len0; i0++){
if(!(validate133(data6[i0], {instancePath:instancePath+"/issues/" + i0,parentData:data6,parentDataProperty:i0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate133.errors : vErrors.concat(validate133.errors);
errors = vErrors.length;
}
}
}
else {
const err12 = {instancePath:instancePath+"/issues",schemaPath:"#/properties/issues/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
else {
const err13 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
validate131.errors = vErrors;
return errors === 0;
}
validate131.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema162 = {"type":"object","additionalProperties":false,"required":["versionId","createdAt","createdBy","message"],"properties":{"versionId":{"$ref":"#/$defs/identifier"},"parentVersionId":{"$ref":"#/$defs/nullableIdentifier"},"createdAt":{"type":"string","format":"date-time"},"createdBy":{"type":"string","minLength":1,"maxLength":200},"message":{"type":"string","maxLength":1000}}};

function validate139(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate139.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.versionId === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "versionId"},message:"must have required property '"+"versionId"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.createdAt === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "createdAt"},message:"must have required property '"+"createdAt"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.createdBy === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "createdBy"},message:"must have required property '"+"createdBy"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.message === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "message"},message:"must have required property '"+"message"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
for(const key0 in data){
if(!(((((key0 === "versionId") || (key0 === "parentVersionId")) || (key0 === "createdAt")) || (key0 === "createdBy")) || (key0 === "message"))){
const err4 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.versionId !== undefined){
let data0 = data.versionId;
if(typeof data0 === "string"){
if(func2(data0) > 160){
const err5 = {instancePath:instancePath+"/versionId",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(func2(data0) < 1){
const err6 = {instancePath:instancePath+"/versionId",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(!pattern4.test(data0)){
const err7 = {instancePath:instancePath+"/versionId",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
else {
const err8 = {instancePath:instancePath+"/versionId",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.parentVersionId !== undefined){
if(!(validate79(data.parentVersionId, {instancePath:instancePath+"/parentVersionId",parentData:data,parentDataProperty:"parentVersionId",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate79.errors : vErrors.concat(validate79.errors);
errors = vErrors.length;
}
}
if(data.createdAt !== undefined){
let data2 = data.createdAt;
if(typeof data2 === "string"){
if(!(formats0.validate(data2))){
const err9 = {instancePath:instancePath+"/createdAt",schemaPath:"#/properties/createdAt/format",keyword:"format",params:{format: "date-time"},message:"must match format \""+"date-time"+"\""};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
else {
const err10 = {instancePath:instancePath+"/createdAt",schemaPath:"#/properties/createdAt/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.createdBy !== undefined){
let data3 = data.createdBy;
if(typeof data3 === "string"){
if(func2(data3) > 200){
const err11 = {instancePath:instancePath+"/createdBy",schemaPath:"#/properties/createdBy/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(func2(data3) < 1){
const err12 = {instancePath:instancePath+"/createdBy",schemaPath:"#/properties/createdBy/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
else {
const err13 = {instancePath:instancePath+"/createdBy",schemaPath:"#/properties/createdBy/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data.message !== undefined){
let data4 = data.message;
if(typeof data4 === "string"){
if(func2(data4) > 1000){
const err14 = {instancePath:instancePath+"/message",schemaPath:"#/properties/message/maxLength",keyword:"maxLength",params:{limit: 1000},message:"must NOT have more than 1000 characters"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
else {
const err15 = {instancePath:instancePath+"/message",schemaPath:"#/properties/message/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
else {
const err16 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
validate139.errors = vErrors;
return errors === 0;
}
validate139.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate20(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
/*# sourceURL="https://mesh2param.dev/schemas/cadgraph/1.0.0" */;
let vErrors = null;
let errors = 0;
const evaluated0 = validate20.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.schemaVersion === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "schemaVersion"},message:"must have required property '"+"schemaVersion"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.id === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.name === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "name"},message:"must have required property '"+"name"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.units === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "units"},message:"must have required property '"+"units"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.sourceCoordinateFrame === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceCoordinateFrame"},message:"must have required property '"+"sourceCoordinateFrame"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.projectTolerance === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "projectTolerance"},message:"must have required property '"+"projectTolerance"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.sketches === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sketches"},message:"must have required property '"+"sketches"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.features === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "features"},message:"must have required property '"+"features"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data.semanticTopology === undefined){
const err8 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "semanticTopology"},message:"must have required property '"+"semanticTopology"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data.sourceEvidence === undefined){
const err9 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "sourceEvidence"},message:"must have required property '"+"sourceEvidence"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data.userLocks === undefined){
const err10 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "userLocks"},message:"must have required property '"+"userLocks"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data.overrides === undefined){
const err11 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "overrides"},message:"must have required property '"+"overrides"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(data.reconstructionSettings === undefined){
const err12 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "reconstructionSettings"},message:"must have required property '"+"reconstructionSettings"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data.engineVersions === undefined){
const err13 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "engineVersions"},message:"must have required property '"+"engineVersions"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data.deterministicSeed === undefined){
const err14 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "deterministicSeed"},message:"must have required property '"+"deterministicSeed"+"'"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(data.fitMetrics === undefined){
const err15 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "fitMetrics"},message:"must have required property '"+"fitMetrics"+"'"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
if(data.validation === undefined){
const err16 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "validation"},message:"must have required property '"+"validation"+"'"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(data.versionMetadata === undefined){
const err17 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "versionMetadata"},message:"must have required property '"+"versionMetadata"+"'"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema31.properties, key0))){
const err18 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.schemaVersion !== undefined){
if("1.0.0" !== data.schemaVersion){
const err19 = {instancePath:instancePath+"/schemaVersion",schemaPath:"#/properties/schemaVersion/const",keyword:"const",params:{allowedValue: "1.0.0"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
if(data.id !== undefined){
let data1 = data.id;
if(typeof data1 === "string"){
if(func2(data1) > 160){
const err20 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/maxLength",keyword:"maxLength",params:{limit: 160},message:"must NOT have more than 160 characters"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
if(func2(data1) < 1){
const err21 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(!pattern4.test(data1)){
const err22 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/pattern",keyword:"pattern",params:{pattern: "^[A-Za-z][A-Za-z0-9._:-]*$"},message:"must match pattern \""+"^[A-Za-z][A-Za-z0-9._:-]*$"+"\""};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
else {
const err23 = {instancePath:instancePath+"/id",schemaPath:"#/$defs/identifier/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.name !== undefined){
let data2 = data.name;
if(typeof data2 === "string"){
if(func2(data2) > 200){
const err24 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(func2(data2) < 1){
const err25 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
else {
const err26 = {instancePath:instancePath+"/name",schemaPath:"#/properties/name/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.units !== undefined){
let data3 = data.units;
if(!(((((data3 === "mm") || (data3 === "cm")) || (data3 === "m")) || (data3 === "in")) || (data3 === "ft"))){
const err27 = {instancePath:instancePath+"/units",schemaPath:"#/$defs/units/enum",keyword:"enum",params:{allowedValues: schema33.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
if(data.source !== undefined){
let data4 = data.source;
const _errs11 = errors;
let valid3 = false;
const _errs12 = errors;
if(!(validate21(data4, {instancePath:instancePath+"/source",parentData:data,parentDataProperty:"source",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate21.errors : vErrors.concat(validate21.errors);
errors = vErrors.length;
}
var _valid0 = _errs12 === errors;
valid3 = valid3 || _valid0;
const _errs13 = errors;
if(data4 !== null){
const err28 = {instancePath:instancePath+"/source",schemaPath:"#/properties/source/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
var _valid0 = _errs13 === errors;
valid3 = valid3 || _valid0;
if(!valid3){
const err29 = {instancePath:instancePath+"/source",schemaPath:"#/properties/source/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
else {
errors = _errs11;
if(vErrors !== null){
if(_errs11){
vErrors.length = _errs11;
}
else {
vErrors = null;
}
}
}
}
if(data.sourceCoordinateFrame !== undefined){
if(!(validate23(data.sourceCoordinateFrame, {instancePath:instancePath+"/sourceCoordinateFrame",parentData:data,parentDataProperty:"sourceCoordinateFrame",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate23.errors : vErrors.concat(validate23.errors);
errors = vErrors.length;
}
}
if(data.projectTolerance !== undefined){
let data6 = data.projectTolerance;
if(data6 && typeof data6 == "object" && !Array.isArray(data6)){
if(data6.surfaceDeviation === undefined){
const err30 = {instancePath:instancePath+"/projectTolerance",schemaPath:"#/$defs/projectTolerance/required",keyword:"required",params:{missingProperty: "surfaceDeviation"},message:"must have required property '"+"surfaceDeviation"+"'"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
if(data6.angularDeviationDeg === undefined){
const err31 = {instancePath:instancePath+"/projectTolerance",schemaPath:"#/$defs/projectTolerance/required",keyword:"required",params:{missingProperty: "angularDeviationDeg"},message:"must have required property '"+"angularDeviationDeg"+"'"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
if(data6.linearResolution === undefined){
const err32 = {instancePath:instancePath+"/projectTolerance",schemaPath:"#/$defs/projectTolerance/required",keyword:"required",params:{missingProperty: "linearResolution"},message:"must have required property '"+"linearResolution"+"'"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
for(const key1 in data6){
if(!(((key1 === "surfaceDeviation") || (key1 === "angularDeviationDeg")) || (key1 === "linearResolution"))){
const err33 = {instancePath:instancePath+"/projectTolerance",schemaPath:"#/$defs/projectTolerance/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
if(data6.surfaceDeviation !== undefined){
let data7 = data6.surfaceDeviation;
if((typeof data7 == "number") && (isFinite(data7))){
if(data7 <= 0 || isNaN(data7)){
const err34 = {instancePath:instancePath+"/projectTolerance/surfaceDeviation",schemaPath:"#/$defs/projectTolerance/properties/surfaceDeviation/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
else {
const err35 = {instancePath:instancePath+"/projectTolerance/surfaceDeviation",schemaPath:"#/$defs/projectTolerance/properties/surfaceDeviation/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
if(data6.angularDeviationDeg !== undefined){
let data8 = data6.angularDeviationDeg;
if((typeof data8 == "number") && (isFinite(data8))){
if(data8 > 180 || isNaN(data8)){
const err36 = {instancePath:instancePath+"/projectTolerance/angularDeviationDeg",schemaPath:"#/$defs/projectTolerance/properties/angularDeviationDeg/maximum",keyword:"maximum",params:{comparison: "<=", limit: 180},message:"must be <= 180"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
if(data8 <= 0 || isNaN(data8)){
const err37 = {instancePath:instancePath+"/projectTolerance/angularDeviationDeg",schemaPath:"#/$defs/projectTolerance/properties/angularDeviationDeg/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
}
else {
const err38 = {instancePath:instancePath+"/projectTolerance/angularDeviationDeg",schemaPath:"#/$defs/projectTolerance/properties/angularDeviationDeg/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
if(data6.linearResolution !== undefined){
let data9 = data6.linearResolution;
if((typeof data9 == "number") && (isFinite(data9))){
if(data9 <= 0 || isNaN(data9)){
const err39 = {instancePath:instancePath+"/projectTolerance/linearResolution",schemaPath:"#/$defs/projectTolerance/properties/linearResolution/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
else {
const err40 = {instancePath:instancePath+"/projectTolerance/linearResolution",schemaPath:"#/$defs/projectTolerance/properties/linearResolution/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
}
else {
const err41 = {instancePath:instancePath+"/projectTolerance",schemaPath:"#/$defs/projectTolerance/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
}
if(data.sketches !== undefined){
let data10 = data.sketches;
if(Array.isArray(data10)){
const len0 = data10.length;
for(let i0=0; i0<len0; i0++){
if(!(validate25(data10[i0], {instancePath:instancePath+"/sketches/" + i0,parentData:data10,parentDataProperty:i0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate25.errors : vErrors.concat(validate25.errors);
errors = vErrors.length;
}
}
}
else {
const err42 = {instancePath:instancePath+"/sketches",schemaPath:"#/properties/sketches/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
}
if(data.features !== undefined){
let data12 = data.features;
if(Array.isArray(data12)){
const len1 = data12.length;
for(let i1=0; i1<len1; i1++){
if(!(validate73(data12[i1], {instancePath:instancePath+"/features/" + i1,parentData:data12,parentDataProperty:i1,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate73.errors : vErrors.concat(validate73.errors);
errors = vErrors.length;
}
}
}
else {
const err43 = {instancePath:instancePath+"/features",schemaPath:"#/properties/features/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
}
}
if(data.semanticTopology !== undefined){
let data14 = data.semanticTopology;
if(Array.isArray(data14)){
const len2 = data14.length;
for(let i2=0; i2<len2; i2++){
if(!(validate122(data14[i2], {instancePath:instancePath+"/semanticTopology/" + i2,parentData:data14,parentDataProperty:i2,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate122.errors : vErrors.concat(validate122.errors);
errors = vErrors.length;
}
}
}
else {
const err44 = {instancePath:instancePath+"/semanticTopology",schemaPath:"#/properties/semanticTopology/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
}
if(data.sourceEvidence !== undefined){
let data16 = data.sourceEvidence;
if(Array.isArray(data16)){
const len3 = data16.length;
for(let i3=0; i3<len3; i3++){
if(!(validate124(data16[i3], {instancePath:instancePath+"/sourceEvidence/" + i3,parentData:data16,parentDataProperty:i3,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate124.errors : vErrors.concat(validate124.errors);
errors = vErrors.length;
}
}
}
else {
const err45 = {instancePath:instancePath+"/sourceEvidence",schemaPath:"#/properties/sourceEvidence/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
}
if(data.userLocks !== undefined){
let data18 = data.userLocks;
if(Array.isArray(data18)){
const len4 = data18.length;
for(let i4=0; i4<len4; i4++){
if(!(validate65(data18[i4], {instancePath:instancePath+"/userLocks/" + i4,parentData:data18,parentDataProperty:i4,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate65.errors : vErrors.concat(validate65.errors);
errors = vErrors.length;
}
}
}
else {
const err46 = {instancePath:instancePath+"/userLocks",schemaPath:"#/properties/userLocks/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err46];
}
else {
vErrors.push(err46);
}
errors++;
}
}
if(data.overrides !== undefined){
let data20 = data.overrides;
if(Array.isArray(data20)){
const len5 = data20.length;
for(let i5=0; i5<len5; i5++){
if(!(validate67(data20[i5], {instancePath:instancePath+"/overrides/" + i5,parentData:data20,parentDataProperty:i5,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate67.errors : vErrors.concat(validate67.errors);
errors = vErrors.length;
}
}
}
else {
const err47 = {instancePath:instancePath+"/overrides",schemaPath:"#/properties/overrides/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err47];
}
else {
vErrors.push(err47);
}
errors++;
}
}
if(data.reconstructionSettings !== undefined){
if(!(validate129(data.reconstructionSettings, {instancePath:instancePath+"/reconstructionSettings",parentData:data,parentDataProperty:"reconstructionSettings",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate129.errors : vErrors.concat(validate129.errors);
errors = vErrors.length;
}
}
if(data.engineVersions !== undefined){
let data23 = data.engineVersions;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.mesh2param === undefined){
const err48 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "mesh2param"},message:"must have required property '"+"mesh2param"+"'"};
if(vErrors === null){
vErrors = [err48];
}
else {
vErrors.push(err48);
}
errors++;
}
if(data23.contracts === undefined){
const err49 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "contracts"},message:"must have required property '"+"contracts"+"'"};
if(vErrors === null){
vErrors = [err49];
}
else {
vErrors.push(err49);
}
errors++;
}
if(data23.cadBackend === undefined){
const err50 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "cadBackend"},message:"must have required property '"+"cadBackend"+"'"};
if(vErrors === null){
vErrors = [err50];
}
else {
vErrors.push(err50);
}
errors++;
}
if(data23.cadQuery === undefined){
const err51 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "cadQuery"},message:"must have required property '"+"cadQuery"+"'"};
if(vErrors === null){
vErrors = [err51];
}
else {
vErrors.push(err51);
}
errors++;
}
if(data23.ocp === undefined){
const err52 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "ocp"},message:"must have required property '"+"ocp"+"'"};
if(vErrors === null){
vErrors = [err52];
}
else {
vErrors.push(err52);
}
errors++;
}
if(data23.dependencies === undefined){
const err53 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/required",keyword:"required",params:{missingProperty: "dependencies"},message:"must have required property '"+"dependencies"+"'"};
if(vErrors === null){
vErrors = [err53];
}
else {
vErrors.push(err53);
}
errors++;
}
for(const key2 in data23){
if(!((((((key2 === "mesh2param") || (key2 === "contracts")) || (key2 === "cadBackend")) || (key2 === "cadQuery")) || (key2 === "ocp")) || (key2 === "dependencies"))){
const err54 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err54];
}
else {
vErrors.push(err54);
}
errors++;
}
}
if(data23.mesh2param !== undefined){
let data24 = data23.mesh2param;
if(typeof data24 === "string"){
if(func2(data24) < 1){
const err55 = {instancePath:instancePath+"/engineVersions/mesh2param",schemaPath:"#/$defs/engineVersions/properties/mesh2param/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err55];
}
else {
vErrors.push(err55);
}
errors++;
}
}
else {
const err56 = {instancePath:instancePath+"/engineVersions/mesh2param",schemaPath:"#/$defs/engineVersions/properties/mesh2param/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err56];
}
else {
vErrors.push(err56);
}
errors++;
}
}
if(data23.contracts !== undefined){
let data25 = data23.contracts;
if(typeof data25 === "string"){
if(func2(data25) < 1){
const err57 = {instancePath:instancePath+"/engineVersions/contracts",schemaPath:"#/$defs/engineVersions/properties/contracts/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err57];
}
else {
vErrors.push(err57);
}
errors++;
}
}
else {
const err58 = {instancePath:instancePath+"/engineVersions/contracts",schemaPath:"#/$defs/engineVersions/properties/contracts/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err58];
}
else {
vErrors.push(err58);
}
errors++;
}
}
if(data23.cadBackend !== undefined){
if("OCCT" !== data23.cadBackend){
const err59 = {instancePath:instancePath+"/engineVersions/cadBackend",schemaPath:"#/$defs/engineVersions/properties/cadBackend/const",keyword:"const",params:{allowedValue: "OCCT"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err59];
}
else {
vErrors.push(err59);
}
errors++;
}
}
if(data23.cadQuery !== undefined){
let data27 = data23.cadQuery;
if(typeof data27 === "string"){
if(func2(data27) < 1){
const err60 = {instancePath:instancePath+"/engineVersions/cadQuery",schemaPath:"#/$defs/engineVersions/properties/cadQuery/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err60];
}
else {
vErrors.push(err60);
}
errors++;
}
}
else {
const err61 = {instancePath:instancePath+"/engineVersions/cadQuery",schemaPath:"#/$defs/engineVersions/properties/cadQuery/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err61];
}
else {
vErrors.push(err61);
}
errors++;
}
}
if(data23.ocp !== undefined){
let data28 = data23.ocp;
if(typeof data28 === "string"){
if(func2(data28) < 1){
const err62 = {instancePath:instancePath+"/engineVersions/ocp",schemaPath:"#/$defs/engineVersions/properties/ocp/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err62];
}
else {
vErrors.push(err62);
}
errors++;
}
}
else {
const err63 = {instancePath:instancePath+"/engineVersions/ocp",schemaPath:"#/$defs/engineVersions/properties/ocp/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err63];
}
else {
vErrors.push(err63);
}
errors++;
}
}
if(data23.dependencies !== undefined){
let data29 = data23.dependencies;
if(data29 && typeof data29 == "object" && !Array.isArray(data29)){
for(const key3 in data29){
if(typeof data29[key3] !== "string"){
const err64 = {instancePath:instancePath+"/engineVersions/dependencies/" + key3.replace(/~/g, "~0").replace(/\//g, "~1"),schemaPath:"#/$defs/engineVersions/properties/dependencies/additionalProperties/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err64];
}
else {
vErrors.push(err64);
}
errors++;
}
}
}
else {
const err65 = {instancePath:instancePath+"/engineVersions/dependencies",schemaPath:"#/$defs/engineVersions/properties/dependencies/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err65];
}
else {
vErrors.push(err65);
}
errors++;
}
}
}
else {
const err66 = {instancePath:instancePath+"/engineVersions",schemaPath:"#/$defs/engineVersions/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err66];
}
else {
vErrors.push(err66);
}
errors++;
}
}
if(data.deterministicSeed !== undefined){
let data31 = data.deterministicSeed;
if(!(((typeof data31 == "number") && (!(data31 % 1) && !isNaN(data31))) && (isFinite(data31)))){
const err67 = {instancePath:instancePath+"/deterministicSeed",schemaPath:"#/properties/deterministicSeed/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err67];
}
else {
vErrors.push(err67);
}
errors++;
}
if((typeof data31 == "number") && (isFinite(data31))){
if(data31 > 4294967295 || isNaN(data31)){
const err68 = {instancePath:instancePath+"/deterministicSeed",schemaPath:"#/properties/deterministicSeed/maximum",keyword:"maximum",params:{comparison: "<=", limit: 4294967295},message:"must be <= 4294967295"};
if(vErrors === null){
vErrors = [err68];
}
else {
vErrors.push(err68);
}
errors++;
}
if(data31 < 0 || isNaN(data31)){
const err69 = {instancePath:instancePath+"/deterministicSeed",schemaPath:"#/properties/deterministicSeed/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err69];
}
else {
vErrors.push(err69);
}
errors++;
}
}
}
if(data.fitMetrics !== undefined){
let data32 = data.fitMetrics;
if(data32 && typeof data32 == "object" && !Array.isArray(data32)){
if(data32.rmsSurfaceDistance === undefined){
const err70 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "rmsSurfaceDistance"},message:"must have required property '"+"rmsSurfaceDistance"+"'"};
if(vErrors === null){
vErrors = [err70];
}
else {
vErrors.push(err70);
}
errors++;
}
if(data32.p95SurfaceDistance === undefined){
const err71 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "p95SurfaceDistance"},message:"must have required property '"+"p95SurfaceDistance"+"'"};
if(vErrors === null){
vErrors = [err71];
}
else {
vErrors.push(err71);
}
errors++;
}
if(data32.maxSurfaceDistance === undefined){
const err72 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "maxSurfaceDistance"},message:"must have required property '"+"maxSurfaceDistance"+"'"};
if(vErrors === null){
vErrors = [err72];
}
else {
vErrors.push(err72);
}
errors++;
}
if(data32.normalAgreement === undefined){
const err73 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "normalAgreement"},message:"must have required property '"+"normalAgreement"+"'"};
if(vErrors === null){
vErrors = [err73];
}
else {
vErrors.push(err73);
}
errors++;
}
if(data32.volumeDifference === undefined){
const err74 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "volumeDifference"},message:"must have required property '"+"volumeDifference"+"'"};
if(vErrors === null){
vErrors = [err74];
}
else {
vErrors.push(err74);
}
errors++;
}
if(data32.overlap === undefined){
const err75 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "overlap"},message:"must have required property '"+"overlap"+"'"};
if(vErrors === null){
vErrors = [err75];
}
else {
vErrors.push(err75);
}
errors++;
}
if(data32.unmatchedSourceArea === undefined){
const err76 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "unmatchedSourceArea"},message:"must have required property '"+"unmatchedSourceArea"+"'"};
if(vErrors === null){
vErrors = [err76];
}
else {
vErrors.push(err76);
}
errors++;
}
if(data32.excessResultArea === undefined){
const err77 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "excessResultArea"},message:"must have required property '"+"excessResultArea"+"'"};
if(vErrors === null){
vErrors = [err77];
}
else {
vErrors.push(err77);
}
errors++;
}
if(data32.score === undefined){
const err78 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/required",keyword:"required",params:{missingProperty: "score"},message:"must have required property '"+"score"+"'"};
if(vErrors === null){
vErrors = [err78];
}
else {
vErrors.push(err78);
}
errors++;
}
for(const key4 in data32){
if(!(func1.call(schema158.properties, key4))){
const err79 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key4},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err79];
}
else {
vErrors.push(err79);
}
errors++;
}
}
if(data32.rmsSurfaceDistance !== undefined){
let data33 = data32.rmsSurfaceDistance;
if((typeof data33 == "number") && (isFinite(data33))){
if(data33 < 0 || isNaN(data33)){
const err80 = {instancePath:instancePath+"/fitMetrics/rmsSurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/rmsSurfaceDistance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err80];
}
else {
vErrors.push(err80);
}
errors++;
}
}
else {
const err81 = {instancePath:instancePath+"/fitMetrics/rmsSurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/rmsSurfaceDistance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err81];
}
else {
vErrors.push(err81);
}
errors++;
}
}
if(data32.p95SurfaceDistance !== undefined){
let data34 = data32.p95SurfaceDistance;
if((typeof data34 == "number") && (isFinite(data34))){
if(data34 < 0 || isNaN(data34)){
const err82 = {instancePath:instancePath+"/fitMetrics/p95SurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/p95SurfaceDistance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err82];
}
else {
vErrors.push(err82);
}
errors++;
}
}
else {
const err83 = {instancePath:instancePath+"/fitMetrics/p95SurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/p95SurfaceDistance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err83];
}
else {
vErrors.push(err83);
}
errors++;
}
}
if(data32.maxSurfaceDistance !== undefined){
let data35 = data32.maxSurfaceDistance;
if((typeof data35 == "number") && (isFinite(data35))){
if(data35 < 0 || isNaN(data35)){
const err84 = {instancePath:instancePath+"/fitMetrics/maxSurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/maxSurfaceDistance/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err84];
}
else {
vErrors.push(err84);
}
errors++;
}
}
else {
const err85 = {instancePath:instancePath+"/fitMetrics/maxSurfaceDistance",schemaPath:"#/$defs/fitMetrics/properties/maxSurfaceDistance/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err85];
}
else {
vErrors.push(err85);
}
errors++;
}
}
if(data32.normalAgreement !== undefined){
let data36 = data32.normalAgreement;
if((typeof data36 == "number") && (isFinite(data36))){
if(data36 > 1 || isNaN(data36)){
const err86 = {instancePath:instancePath+"/fitMetrics/normalAgreement",schemaPath:"#/$defs/fitMetrics/properties/normalAgreement/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err86];
}
else {
vErrors.push(err86);
}
errors++;
}
if(data36 < 0 || isNaN(data36)){
const err87 = {instancePath:instancePath+"/fitMetrics/normalAgreement",schemaPath:"#/$defs/fitMetrics/properties/normalAgreement/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err87];
}
else {
vErrors.push(err87);
}
errors++;
}
}
else {
const err88 = {instancePath:instancePath+"/fitMetrics/normalAgreement",schemaPath:"#/$defs/fitMetrics/properties/normalAgreement/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err88];
}
else {
vErrors.push(err88);
}
errors++;
}
}
if(data32.volumeDifference !== undefined){
let data37 = data32.volumeDifference;
if((typeof data37 == "number") && (isFinite(data37))){
if(data37 < 0 || isNaN(data37)){
const err89 = {instancePath:instancePath+"/fitMetrics/volumeDifference",schemaPath:"#/$defs/fitMetrics/properties/volumeDifference/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err89];
}
else {
vErrors.push(err89);
}
errors++;
}
}
else {
const err90 = {instancePath:instancePath+"/fitMetrics/volumeDifference",schemaPath:"#/$defs/fitMetrics/properties/volumeDifference/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err90];
}
else {
vErrors.push(err90);
}
errors++;
}
}
if(data32.overlap !== undefined){
let data38 = data32.overlap;
if((typeof data38 == "number") && (isFinite(data38))){
if(data38 > 1 || isNaN(data38)){
const err91 = {instancePath:instancePath+"/fitMetrics/overlap",schemaPath:"#/$defs/fitMetrics/properties/overlap/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err91];
}
else {
vErrors.push(err91);
}
errors++;
}
if(data38 < 0 || isNaN(data38)){
const err92 = {instancePath:instancePath+"/fitMetrics/overlap",schemaPath:"#/$defs/fitMetrics/properties/overlap/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err92];
}
else {
vErrors.push(err92);
}
errors++;
}
}
else {
const err93 = {instancePath:instancePath+"/fitMetrics/overlap",schemaPath:"#/$defs/fitMetrics/properties/overlap/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err93];
}
else {
vErrors.push(err93);
}
errors++;
}
}
if(data32.unmatchedSourceArea !== undefined){
let data39 = data32.unmatchedSourceArea;
if((typeof data39 == "number") && (isFinite(data39))){
if(data39 < 0 || isNaN(data39)){
const err94 = {instancePath:instancePath+"/fitMetrics/unmatchedSourceArea",schemaPath:"#/$defs/fitMetrics/properties/unmatchedSourceArea/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err94];
}
else {
vErrors.push(err94);
}
errors++;
}
}
else {
const err95 = {instancePath:instancePath+"/fitMetrics/unmatchedSourceArea",schemaPath:"#/$defs/fitMetrics/properties/unmatchedSourceArea/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err95];
}
else {
vErrors.push(err95);
}
errors++;
}
}
if(data32.excessResultArea !== undefined){
let data40 = data32.excessResultArea;
if((typeof data40 == "number") && (isFinite(data40))){
if(data40 < 0 || isNaN(data40)){
const err96 = {instancePath:instancePath+"/fitMetrics/excessResultArea",schemaPath:"#/$defs/fitMetrics/properties/excessResultArea/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err96];
}
else {
vErrors.push(err96);
}
errors++;
}
}
else {
const err97 = {instancePath:instancePath+"/fitMetrics/excessResultArea",schemaPath:"#/$defs/fitMetrics/properties/excessResultArea/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err97];
}
else {
vErrors.push(err97);
}
errors++;
}
}
if(data32.score !== undefined){
let data41 = data32.score;
if(!((typeof data41 == "number") && (isFinite(data41)))){
const err98 = {instancePath:instancePath+"/fitMetrics/score",schemaPath:"#/$defs/fitMetrics/properties/score/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err98];
}
else {
vErrors.push(err98);
}
errors++;
}
}
}
else {
const err99 = {instancePath:instancePath+"/fitMetrics",schemaPath:"#/$defs/fitMetrics/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err99];
}
else {
vErrors.push(err99);
}
errors++;
}
}
if(data.validation !== undefined){
if(!(validate131(data.validation, {instancePath:instancePath+"/validation",parentData:data,parentDataProperty:"validation",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate131.errors : vErrors.concat(validate131.errors);
errors = vErrors.length;
}
}
if(data.versionMetadata !== undefined){
if(!(validate139(data.versionMetadata, {instancePath:instancePath+"/versionMetadata",parentData:data,parentDataProperty:"versionMetadata",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate139.errors : vErrors.concat(validate139.errors);
errors = vErrors.length;
}
}
if(data.extensions !== undefined){
let data44 = data.extensions;
if((!(data44 && typeof data44 == "object" && !Array.isArray(data44))) && (data44 !== null)){
const err100 = {instancePath:instancePath+"/extensions",schemaPath:"#/properties/extensions/type",keyword:"type",params:{type: schema31.properties.extensions.type},message:"must be object,null"};
if(vErrors === null){
vErrors = [err100];
}
else {
vErrors.push(err100);
}
errors++;
}
if(data44 && typeof data44 == "object" && !Array.isArray(data44)){
for(const key5 in data44){
const _errs91 = errors;
if(typeof key5 === "string"){
if(!pattern46.test(key5)){
const err101 = {instancePath:instancePath+"/extensions",schemaPath:"#/properties/extensions/propertyNames/pattern",keyword:"pattern",params:{pattern: "^[a-z][a-z0-9.-]+/[A-Za-z0-9._-]+$"},message:"must match pattern \""+"^[a-z][a-z0-9.-]+/[A-Za-z0-9._-]+$"+"\"",propertyName:key5};
if(vErrors === null){
vErrors = [err101];
}
else {
vErrors.push(err101);
}
errors++;
}
}
var valid23 = _errs91 === errors;
if(!valid23){
const err102 = {instancePath:instancePath+"/extensions",schemaPath:"#/properties/extensions/propertyNames",keyword:"propertyNames",params:{propertyName: key5},message:"property name must be valid"};
if(vErrors === null){
vErrors = [err102];
}
else {
vErrors.push(err102);
}
errors++;
}
}
for(const key6 in data44){
if(!(validate68(data44[key6], {instancePath:instancePath+"/extensions/" + key6.replace(/~/g, "~0").replace(/\//g, "~1"),parentData:data44,parentDataProperty:key6,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate68.errors : vErrors.concat(validate68.errors);
errors = vErrors.length;
}
}
}
}
}
else {
const err103 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err103];
}
else {
vErrors.push(err103);
}
errors++;
}
validate20.errors = vErrors;
return errors === 0;
}
validate20.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


export interface SchemaValidationResult {
  valid: boolean;
  errors: ErrorObject[];
}

export function validateCADGraphSchema(value: unknown): SchemaValidationResult {
  const valid = validate(value);
  return { valid, errors: valid ? [] : [...(validate.errors ?? [])] };
}
