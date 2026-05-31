init = 0.25118488;

n = 94;
F = Array[f, n];

Imux = Join[{0.91, 0.91, 0.91, 0.546}, 
   ConstantArray[0.91, 11], {0.546}, ConstantArray[0.91, 6], {0}, 
   ConstantArray[0.91, 2], {0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 
    0.546, 0.91, 0.546}, ConstantArray[0.91, 8], {0.546}, 
   ConstantArray[0.91, 13], {0.546}, 
   ConstantArray[0.91, 13], {0.546, 0.546}, 
   ConstantArray[0.91, 8], {0.546}, ConstantArray[0.91, 14]];
Imuz = Join[{0.91, 0.91, 0.91, 0.546}, 
   ConstantArray[0.91, 11], {0.546}, 
   ConstantArray[0.91, 9], {0.546, 0.91, 0.546, 0.91, 0.546, 0.91, 
    0.546, 0.91, 0.546}, ConstantArray[0.91, 8], {0.546}, 
   ConstantArray[0.91, 2], {0}, ConstantArray[0.91, 10], {0.546}, 
   ConstantArray[0.91, 9], {0}, ConstantArray[0.91, 3], {0.546, 0.546},
    ConstantArray[0.91, 8], {0.546}, ConstantArray[0.91, 14]];

Mmu = Join[{init, 0.02548, 0.02548, 0.3274}, 
   ConstantArray[0.02548, 11], {0.3274}, 
   ConstantArray[0.02548, 9], {0.3274, 0.02548, 0.3274, 0.02548, 
    0.3274, 0.02548, 0.3274, 0.02548, 0.3274}, 
   ConstantArray[0.026, 8], {0.3274}, 
   ConstantArray[0.026, 13], {0.3274}, 
   ConstantArray[0.026, 13], {0.13, 0.3274}, 
   ConstantArray[0.026, 8], {0.3274}, ConstantArray[0.026, 14]];

coefFromIToT[imu_List, t_Integer] := 
  Module[{c = ConstantArray[0., t]}, c[[t]] = 1.;
   Do[c[[i]] = 1. + imu[[i]]*c[[i + 1]], {i, t - 1, 1, -1}];
   c];

cXAll = Table[coefFromIToT[Imux, t], {t, 1, n}];
cZAll = Table[coefFromIToT[Imuz, t], {t, 1, n}];

Mmux[F_List] := ReplacePart[Take[Mmu, Length[F]]*Sin[F], {}];
Mmuz[F_List] := ReplacePart[Take[Mmu, Length[F]]*Cos[F], {}];

X[_, t_Integer /; t <= 0] := 0.;
Z[_, t_Integer /; t <= 0] := 0.;

X[F_List, t_Integer?Positive] := cXAll[[t]] . Mmux[F[[;; t]]];
Z[F_List, t_Integer?Positive] := cZAll[[t]] . Mmuz[F[[;; t]]];

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

obj = X[F, n];
cons = {
   F[[1]] == -145.10517607*Pi/180,
   Z[F, 0] - Z[F, m1] <= zoff + 219.4874,
   X[F, 0] - X[F, m1] >= xoff - 667.2999,
   X[F, 0] - X[F, m3] >= xoff - 666.2999,
   X[F, 0] - X[F, m4] >= xoff - 666.2999,
   Z[F, 0] - Z[F, m4 + 1] <= zoff + 227.6999,
   X[F, 0] - X[F, m5 + 1] >= xoff - 666.6999,
   Z[F, 0] - Z[F, m5 + 1] <= zoff + 228.2999,
   Z[F, 0] - Z[F, m6] >= zoff + 228.3001,
   Z[F, 0] - Z[F, m6 + 1] <= zoff + 228.6999,
   Z[F, 0] - Z[F, m7] >= zoff + 228.7001,
   X[F, 0] - X[F, m7] >= xoff - 668.2999,
   X[F, 0] - X[F, m8] <= xoff - 671.7002,
   Z[F, 0] - Z[F, m8a] <= zoff + 230.2998,
   Z[F, 0] - Z[F, m8b] >= zoff + 230.3002,
   X[F, 0] - X[F, m8b] >= xoff - 672.6998,
   Z[F, 0] - Z[F, m8c - 1] >= zoff + 230.3002,
   X[F, 0] - X[F, m8c] <= xoff - 674.3002,
   Z[F, 0] - Z[F, m9] <= zoff + 229.4873,
   Z[F, 0] - Z[F, m9a] >= zoff + 229.3002,
   X[F, 0] - X[F, m9a] >= xoff - 676.2998,
   Z[F, 0] - Z[F, m9b] <= zoff + 228.6998,
   X[F, 0] - X[F, m9b] >= xoff - 678.1373,
   X[F, 0] - X[F, m10] <= xoff - 680.0753,
   X[F, 0] - X[F, m10a] >= xoff - 680.9247,
   Z[F, 0] - Z[F, m10a] <= zoff + 228.6122,
   X[F, 0] - X[F, m10b] <= xoff - 681.3003,
   Z[F, 0] - Z[F, m10b - 1] >= zoff + 228.3003,
   X[F, 0] - X[F, m11] >= xoff - 681.6122,
   Z[F, 0] - Z[F, m11] >= zoff + 227.0747,
   X[F, 0] - X[F, m11a] >= xoff - 684.6997,
   Z[F, 0] - Z[F, m11a] <= zoff + 224.6997,
   (*Z[F,0]-Z[F,m12]>=zoff+224.3875*)
   X[F, m2 + 8] - X[F, m2 + 9] <= 0.0054,
   X[F, m2 + 9] - X[F, m2 + 8] <= 0.0054,
   Z[F, m8 + 4] - Z[F, m8 + 5] <= 0.0054,
   Z[F, m8 + 5] - Z[F, m8 + 4] <= 0.0054,
   Z[F, m9 + 11] - Z[F, m9 + 12] <= 0.0054,
   Z[F, m9 + 12] - Z[F, m9 + 11] <= 0.0054
   };

sol = NMaximize[{obj, cons}, F, AccuracyGoal -> 20, 
   PrecisionGoal -> 20];
fopt = F /. sol[[2]];
vel = Table[{X[fopt, t] - X[fopt, t - 1], 
   Z[fopt, t] - Z[fopt, t - 1]}, {t, 0, n}]
points = 
  Table[{X[fopt, t] - X[fopt, 0] + xoff, 
    Z[fopt, t] - Z[fopt, 0] + zoff}, {t, 0, n}];
NumberForm[points, {Infinity, 5}]
ListLinePlot[points, AspectRatio -> Full, 
 GridLines -> {{0, 1, 2}, {-1, 0, 1, 2, 3}}, 
 PlotStyle -> PointSize[0.03], PlotMarkers -> Automatic]
(fopt*180/Pi)
fopt2 = Round[1000*(Mod[((fopt*180/Pi) + 180), 360] - 180)]*0.001
turn = Table[fopt2[[t]] - fopt2[[t - 1]], {t, 2, n}]