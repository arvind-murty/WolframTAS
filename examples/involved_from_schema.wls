(* Generated from examples/involved_mathematica_input.json. *)
(* Regenerate with: python3 -m wolframtas_orchestrator render-mathematica <input.json> --out <output.wls> *)
(* Plotting, turn calculation, and output formatting are intentionally omitted. *)

n = 94;
F = Array[f, n];

m1 = 2;
m2 = 14;
m3 = 24;
m4 = 26;
m5 = 28;
m6 = 30;
m7 = 32;
m8 = 41;
m8a = 41;
m8b = 43;
m8c = 49;
m9 = 55;
m9a = 56;
m9b = 62;
m10 = 69;
m10a = 70;
m10b = 74;
m11 = 79;
m11a = 92;
m12 = 94;
zoff = -219.09404548;
xoff = 667.44389288;

Imux = {
  0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0, 0.91,
  0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.546,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91
};

Imuz = {
  0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91,
  0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0, 0.91, 0.91, 0.91, 0.546, 0.546,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.546, 0.91, 0.91, 0.91,
  0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91, 0.91
};

Mmu = {
  0.25118488, 0.02548, 0.02548, 0.3274, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548,
  0.02548, 0.02548, 0.02548, 0.3274, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548, 0.02548,
  0.02548, 0.3274, 0.02548, 0.3274, 0.02548, 0.3274, 0.02548, 0.3274, 0.02548, 0.3274, 0.026, 0.026,
  0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.3274, 0.026, 0.026, 0.026, 0.026, 0.026,
  0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.3274, 0.026, 0.026, 0.026,
  0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.13, 0.3274,
  0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.3274, 0.026, 0.026, 0.026,
  0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026, 0.026
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

obj = X[F, m12];

cons = {
  (* fixed_initial_direction *)
  F[[1]] == -145.10517607*Pi/180,
  (* m1_z_upper *)
  Z[F, 0] - Z[F, m1] <= zoff + 219.4874,
  (* m1_x_lower *)
  X[F, 0] - X[F, m1] >= xoff - 667.2999,
  (* m3_x_lower *)
  X[F, 0] - X[F, m3] >= xoff - 666.2999,
  (* m4_x_lower *)
  X[F, 0] - X[F, m4] >= xoff - 666.2999,
  (* m4_plus_1_z_upper *)
  Z[F, 0] - Z[F, m4 + 1] <= zoff + 227.6999,
  (* m5_plus_1_x_lower *)
  X[F, 0] - X[F, m5 + 1] >= xoff - 666.6999,
  (* m5_plus_1_z_upper *)
  Z[F, 0] - Z[F, m5 + 1] <= zoff + 228.2999,
  (* m6_z_lower *)
  Z[F, 0] - Z[F, m6] >= zoff + 228.3001,
  (* m6_plus_1_z_upper *)
  Z[F, 0] - Z[F, m6 + 1] <= zoff + 228.6999,
  (* m7_z_lower *)
  Z[F, 0] - Z[F, m7] >= zoff + 228.7001,
  (* m7_x_lower *)
  X[F, 0] - X[F, m7] >= xoff - 668.2999,
  (* m8_x_upper *)
  X[F, 0] - X[F, m8] <= xoff - 671.7002,
  (* m8a_z_upper *)
  Z[F, 0] - Z[F, m8a] <= zoff + 230.2998,
  (* m8b_z_lower *)
  Z[F, 0] - Z[F, m8b] >= zoff + 230.3002,
  (* m8b_x_lower *)
  X[F, 0] - X[F, m8b] >= xoff - 672.6998,
  (* m8c_minus_1_z_lower *)
  Z[F, 0] - Z[F, m8c - 1] >= zoff + 230.3002,
  (* m8c_x_upper *)
  X[F, 0] - X[F, m8c] <= xoff - 674.3002,
  (* m9_z_upper *)
  Z[F, 0] - Z[F, m9] <= zoff + 229.4873,
  (* m9a_z_lower *)
  Z[F, 0] - Z[F, m9a] >= zoff + 229.3002,
  (* m9a_x_lower *)
  X[F, 0] - X[F, m9a] >= xoff - 676.2998,
  (* m9b_z_upper *)
  Z[F, 0] - Z[F, m9b] <= zoff + 228.6998,
  (* m9b_x_lower *)
  X[F, 0] - X[F, m9b] >= xoff - 678.1373,
  (* m10_x_upper *)
  X[F, 0] - X[F, m10] <= xoff - 680.0753,
  (* m10a_x_lower *)
  X[F, 0] - X[F, m10a] >= xoff - 680.9247,
  (* m10a_z_upper *)
  Z[F, 0] - Z[F, m10a] <= zoff + 228.6122,
  (* m10b_x_upper *)
  X[F, 0] - X[F, m10b] <= xoff - 681.3003,
  (* m10b_minus_1_z_lower *)
  Z[F, 0] - Z[F, m10b - 1] >= zoff + 228.3003,
  (* m11_x_lower *)
  X[F, 0] - X[F, m11] >= xoff - 681.6122,
  (* m11_z_lower *)
  Z[F, 0] - Z[F, m11] >= zoff + 227.0747,
  (* m11a_x_lower *)
  X[F, 0] - X[F, m11a] >= xoff - 684.6997,
  (* m11a_z_upper *)
  Z[F, 0] - Z[F, m11a] <= zoff + 224.6997,
  (* x_inertia_raw_upper *)
  X[F, m2 + 8] - X[F, m2 + 9] <= 0.0054,
  (* x_inertia_raw_lower *)
  X[F, m2 + 9] - X[F, m2 + 8] <= 0.0054,
  (* z_inertia_raw_upper_m8 *)
  Z[F, m8 + 4] - Z[F, m8 + 5] <= 0.0054,
  (* z_inertia_raw_lower_m8 *)
  Z[F, m8 + 5] - Z[F, m8 + 4] <= 0.0054,
  (* z_inertia_raw_upper_m9 *)
  Z[F, m9 + 11] - Z[F, m9 + 12] <= 0.0054,
  (* z_inertia_raw_lower_m9 *)
  Z[F, m9 + 12] - Z[F, m9 + 11] <= 0.0054
};

sol = NMaximize[{obj, cons}, F, AccuracyGoal -> 20,
  PrecisionGoal -> 20];
fopt = F /. sol[[2]];

points = Table[{X[fopt, t] - X[fopt, 0] + xoff,
  Z[fopt, t] - Z[fopt, 0] + zoff}, {t, 0, n}];
NumberForm[points, {Infinity, 5}]
