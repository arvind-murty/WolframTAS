init = 0;

n = 17;
F = Array[f, n];

Imux = Join[ConstantArray[0.91, 4], ConstantArray[0.8, 20]];
Imuz = Join[ConstantArray[0.91, 4], ConstantArray[0.8, 20]];

Mmu = Join[{0.02, 0.02, 0.026, 0.026}, ConstantArray[0.02, 20]];

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

m1 = 17;

zoff = -246.7;
xoff = 681.30043298;

obj = Z[F, m1] - Z[F, m1 - 1];
cons = {
   X[F, 0] - X[F, m1] >= xoff - 680.3,
   Z[F, 0] - Z[F, m1] <= zoff + 245.6999,
   Z[F, 0] - Z[F, m1] >= zoff + 245.699
   };

sol = NMaximize[{obj, cons}, F, AccuracyGoal -> 20, 
   PrecisionGoal -> 20];
fopt = F /. sol[[2]];
vel = Table[{X[fopt, t] - X[fopt, t - 1], 
   Z[fopt, t] - Z[fopt, t - 1]}, {t, 0, n}];
points = 
  Table[{X[fopt, t] - X[fopt, 0] + xoff, 
    Z[fopt, t] - Z[fopt, 0] + zoff}, {t, 0, n}];
Print[NumberForm[points, {Infinity, 5}]];
(fopt*180/Pi);
fopt2 = Round[1000*(Mod[((fopt*180/Pi) + 180), 360] - 180)]*0.001;
turn = Table[fopt2[[t]] - fopt2[[t - 1]], {t, 2, n}];