#!/usr/bin/env wolframscript

failureTag = Unique["wolframtasFailure"];

fail[message_String] := Throw[
  <|"version" -> 1, "status" -> "error", "diagnostics" -> <|"message" -> message|>|>,
  failureTag
];

getRequired[assoc_Association, key_String] := If[KeyExistsQ[assoc, key], assoc[key], fail["Missing required key: " <> key]];

validateNumberList[name_String, values_, n_Integer] := Module[{},
  If[!ListQ[values], fail[name <> " must be a list"]];
  If[Length[values] < n, fail[name <> " must contain at least n values"]];
  If[!AllTrue[values, NumericQ], fail[name <> " must contain only numbers"]];
  values
];

validateSymbolName[name_String] := If[
  !StringMatchQ[name, RegularExpression["[A-Za-z][A-Za-z0-9_]*"]],
  fail["Invalid constant name: " <> name]
];

assignConstant[name_String, value_] := Module[{},
  validateSymbolName[name];
  If[!NumericQ[value], fail["Constant must be numeric: " <> name]];
  ToExpression[name, InputForm, Function[symbol, symbol = value, HoldAll]];
];

makeOverrideRules[overrides_, target_String, n_Integer] := Module[{selected},
  If[!ListQ[overrides], fail["component_overrides must be a list"]];
  selected = Select[overrides, AssociationQ[#] && Lookup[#, "target", ""] == target &];
  Map[
    Function[override,
      Module[{slot = getRequired[override, "slot"], value = getRequired[override, "value"]},
        If[!IntegerQ[slot] || slot < 1 || slot > n, fail["Invalid override slot for " <> target]];
        If[!NumericQ[value], fail["Override value must be numeric for " <> target]];
        slot -> value
      ]
    ],
    selected
  ]
];

inertiaVelocity[axis_String, slot_Integer] := If[
  axis == "x",
  X[F, slot] - X[F, slot - 1],
  Z[F, slot] - Z[F, slot - 1]
];

makeInertiaConstraint[event_, n_Integer] := Module[
  {
    eventType, axis, slot, direction, threshold, retentionMultiplier,
    velocity
  },
  If[!AssociationQ[event], fail["Each inertia_events entry must be an object"]];
  eventType = getRequired[event, "type"];
  axis = getRequired[event, "axis"];
  slot = getRequired[event, "slot"];
  direction = Lookup[event, "direction", ""];
  threshold = Lookup[event, "threshold", 0.005];
  retentionMultiplier = getRequired[event, "retention_multiplier"];
  If[!MemberQ[{"hit", "avoid"}, eventType], fail["inertia_events.type must be hit or avoid"]];
  If[!MemberQ[{"x", "z"}, axis], fail["inertia_events.axis must be x or z"]];
  If[!IntegerQ[slot] || slot < 1 || slot > n, fail["Invalid inertia_events slot"]];
  If[!NumericQ[threshold] || threshold <= 0, fail["inertia_events.threshold must be positive"]];
  If[!NumericQ[retentionMultiplier], fail["inertia_events.retention_multiplier must be numeric"]];
  velocity = retentionMultiplier*inertiaVelocity[axis, slot];
  If[eventType == "hit",
    {velocity <= threshold, -velocity <= threshold},
    If[!MemberQ[{"positive", "negative"}, direction], fail["inertia_events.direction must be positive or negative for avoid"]];
    If[direction == "positive", velocity >= threshold, -velocity >= threshold]
  ]
];

optimizerPrecisionValue[value_] := If[
  StringQ[value],
  Switch[value,
    "MachinePrecision", MachinePrecision,
    "Automatic", Automatic,
    _, fail["optimizer.working_precision string must be MachinePrecision or Automatic"]
  ],
  value
];

coefFromIToT[imu_List, t_Integer] := Module[{c = ConstantArray[0., t]},
  c[[t]] = 1.;
  Do[c[[i]] = 1. + imu[[i]]*c[[i + 1]], {i, t - 1, 1, -1}];
  c
];

wrapDegrees[radians_] := Mod[(radians*180/Pi) + 180, 360] - 180;

buildPoint[slot_Integer, fopt_List, constants_Association] := Module[{x = N[X[fopt, slot]], z = N[Z[fopt, slot]], base},
  base = <|"slot" -> slot, "x" -> x, "z" -> z|>;
  If[KeyExistsQ[constants, "xoff"] && KeyExistsQ[constants, "zoff"],
    Join[base, <|"world_x" -> N[x + constants["xoff"]], "world_z" -> N[z + constants["zoff"]]|>],
    base
  ]
];

run[] := Module[
  {
    args, inputPath, problem, arrays, constants, objectiveSpec, constraintSpecs,
    inertiaEvents, overrides, optimizer, n, sense, objectiveExpression, constraintExpressions,
    mmuxOverrideRules, mmuzOverrideRules, solution, objectiveValue, rules, fopt,
    accuracyGoal, precisionGoal, workingPrecision, maxIterations, method, optimizerOptions, status
  },

  args = $ScriptCommandLine;
  If[Length[args] < 2, fail["Usage: wolframscript -file mathematica/optimize.wls path/to/problem.json"]];
  inputPath = Last[args];
  If[!FileExistsQ[inputPath], fail["Input JSON file does not exist: " <> inputPath]];

  problem = Import[inputPath, "RawJSON"];
  If[!AssociationQ[problem], fail["Input JSON must be an object"]];
  If[getRequired[problem, "version"] =!= 1, fail["Unsupported input version"]];
  If[Lookup[problem, "slot_indexing", "1_based"] =!= "1_based", fail["Only 1_based slot indexing is supported"]];

  n = getRequired[problem, "n"];
  If[!IntegerQ[n] || n < 1, fail["n must be a positive integer"]];

  arrays = getRequired[problem, "arrays"];
  If[!AssociationQ[arrays], fail["arrays must be an object"]];
  Imux = validateNumberList["arrays.imux", getRequired[arrays, "imux"], n];
  Imuz = validateNumberList["arrays.imuz", getRequired[arrays, "imuz"], n];
  Mmu = validateNumberList["arrays.mmu", getRequired[arrays, "mmu"], n];

  constants = Lookup[problem, "constants", <||>];
  If[!AssociationQ[constants], fail["constants must be an object"]];
  KeyValueMap[assignConstant, constants];

  overrides = Lookup[problem, "component_overrides", {}];
  mmuxOverrideRules = makeOverrideRules[overrides, "mmux", n];
  mmuzOverrideRules = makeOverrideRules[overrides, "mmuz", n];

  F = Array[f, n];
  cXAll = Table[coefFromIToT[Imux, t], {t, 1, n}];
  cZAll = Table[coefFromIToT[Imuz, t], {t, 1, n}];

  Clear[Mmux, Mmuz, X, Z];
  Mmux[angles_List] := ReplacePart[Take[Mmu, Length[angles]]*Sin[angles], mmuxOverrideRules];
  Mmuz[angles_List] := ReplacePart[Take[Mmu, Length[angles]]*Cos[angles], mmuzOverrideRules];
  X[_, t_Integer /; t <= 0] := 0.;
  Z[_, t_Integer /; t <= 0] := 0.;
  X[angles_List, t_Integer?Positive] := cXAll[[t]] . Mmux[angles[[;; t]]];
  Z[angles_List, t_Integer?Positive] := cZAll[[t]] . Mmuz[angles[[;; t]]];

  objectiveSpec = getRequired[problem, "objective"];
  If[!AssociationQ[objectiveSpec], fail["objective must be an object"]];
  sense = Lookup[objectiveSpec, "sense", "maximize"];
  If[!MemberQ[{"maximize", "minimize"}, sense], fail["objective.sense must be maximize or minimize"]];
  objectiveExpression = ToExpression[getRequired[objectiveSpec, "expression"]];

  constraintSpecs = Lookup[problem, "constraints", {}];
  If[!ListQ[constraintSpecs], fail["constraints must be a list"]];
  constraintExpressions = Map[
    Function[constraint,
      If[!AssociationQ[constraint], fail["Each constraint must be an object"]];
      ToExpression[getRequired[constraint, "expression"]]
    ],
    constraintSpecs
  ];

  inertiaEvents = Lookup[problem, "inertia_events", {}];
  If[!ListQ[inertiaEvents], fail["inertia_events must be a list"]];
  constraintExpressions = Join[constraintExpressions, Flatten[Map[makeInertiaConstraint[#, n] &, inertiaEvents]]];

  optimizer = Lookup[problem, "optimizer", <||>];
  If[!AssociationQ[optimizer], fail["optimizer must be an object"]];
  accuracyGoal = Lookup[optimizer, "accuracy_goal", 20];
  precisionGoal = Lookup[optimizer, "precision_goal", 20];
  workingPrecision = optimizerPrecisionValue[Lookup[optimizer, "working_precision", Automatic]];
  maxIterations = Lookup[optimizer, "max_iterations", Automatic];
  method = Lookup[optimizer, "method", Automatic];
  optimizerOptions = {AccuracyGoal -> accuracyGoal, PrecisionGoal -> precisionGoal};
  If[workingPrecision =!= Automatic, optimizerOptions = Append[optimizerOptions, WorkingPrecision -> workingPrecision]];
  If[maxIterations =!= Automatic, optimizerOptions = Append[optimizerOptions, MaxIterations -> maxIterations]];
  If[method =!= Automatic, optimizerOptions = Append[optimizerOptions, Method -> method]];

  solution = Quiet[
    If[sense == "maximize",
      NMaximize[{objectiveExpression, constraintExpressions}, F, Sequence @@ optimizerOptions],
      NMinimize[{objectiveExpression, constraintExpressions}, F, Sequence @@ optimizerOptions]
    ]
  ];

  If[!ListQ[solution] || Length[solution] != 2, fail["Optimizer did not return a solution pair"]];

  objectiveValue = N[solution[[1]]];
  rules = solution[[2]];
  fopt = F /. rules;
  If[!ListQ[fopt] || Length[fopt] != n || !AllTrue[fopt, NumericQ],
    fail["Optimizer did not return numeric movement directions"]
  ];

  status = If[NumericQ[objectiveValue], "optimal", "feasible"];
  <|
    "version" -> 1,
    "status" -> status,
    "objective_value" -> objectiveValue,
    "movement_directions" -> Table[
      <|"slot" -> slot, "radians" -> N[fopt[[slot]]], "degrees" -> N[wrapDegrees[fopt[[slot]]]]|>,
      {slot, 1, n}
    ],
    "points" -> Table[buildPoint[slot, fopt, constants], {slot, 0, n}],
    "diagnostics" -> <|
      "name" -> Lookup[problem, "name", ""],
      "sense" -> sense,
      "component_override_count" -> Length[overrides],
      "inertia_event_count" -> Length[inertiaEvents]
    |>
  |>
];

result = Catch[run[], failureTag];
Print[ExportString[result, "RawJSON"]];
If[AssociationQ[result] && Lookup[result, "status", "error"] === "error", Exit[1], Exit[0]];
