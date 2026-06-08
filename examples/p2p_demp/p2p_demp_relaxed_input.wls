(* Generated from /Users/arvind.murty/WolframTAS/examples/p2p_demp/p2p_demp_relaxed_input.json. *)
(* Regenerate with: python3 -m wolframtas_orchestrator render-mathematica <input.json> --out <output.wls> *)
(* Plotting, turn calculation, and output formatting are intentionally omitted. *)

n = 12;
F = Array[f, n];


Imux = {
  0.546000063419342, 0.546000063419342, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437
};

Imuz = {
  0.546000063419342, 0.546000063419342, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437, 0.9100000262260437
};

Mmu = {
  0.31, 0.32739998618364297, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654, 0.025999998673796654
};

coefFromIToT[imu_List, t_Integer] := Module[{c = ConstantArray[0., t]},
  c[[t]] = 1.;
  Do[c[[i]] = 1. + imu[[i]]*c[[i + 1]], {i, t - 1, 1, -1}];
  c
];

cXAll = Table[coefFromIToT[Imux, t], {t, 1, n}];
cZAll = Table[coefFromIToT[Imuz, t], {t, 1, n}];

mmuxOverrideRules = {};
mmuzOverrideRules = {};

Mmux[F_List] := ReplacePart[Take[Mmu, Length[F]]*Sin[F], mmuxOverrideRules];
Mmuz[F_List] := ReplacePart[Take[Mmu, Length[F]]*Cos[F], mmuzOverrideRules];

X[_, t_Integer /; t <= 0] := 0.;
Z[_, t_Integer /; t <= 0] := 0.;

X[F_List, t_Integer?Positive] := cXAll[[t]] . Mmux[F[[;; t]]];
Z[F_List, t_Integer?Positive] := cZAll[[t]] . Mmuz[F[[;; t]]];

obj = X[F, 12];

cons = {
  (* x_2_0_min *)
  X[F, 2] - X[F, 0] >= 0.4376,
  (* x_8_0_min *)
  X[F, 8] - X[F, 0] >= 0.4376,
  (* z_8_1_min *)
  Z[F, 8] - Z[F, 1] >= 1.6001
};

sol = NMinimize[{obj, cons}, F, AccuracyGoal -> 20,
  PrecisionGoal -> 20];
fopt = F /. sol[[2]];

points = Table[{X[fopt, t] - X[fopt, 0] + xoff,
  Z[fopt, t] - Z[fopt, 0] + zoff}, {t, 0, n}];
NumberForm[points, {Infinity, 5}]
