% Vorstudie TaskBuddy: Wochenplan als Constraint-Modell (gleiches Modell wie die CP-SAT-Variante)
include "disjunctive.mzn";

int: nW;                         % Zeitfenster
array[1..nW] of int: wday;       % Tag 0..6
array[1..nW] of int: wstart;     % Beginn (15-min-Schritte ab Mo 00:00)
array[1..nW] of int: wend;       % Ende
array[1..nW] of bool: wlb;       % true = Lernbuero-Stunde
array[1..nW] of set of int: wfaecher;  % im Lernbuero angebotene Faecher

int: nB;                         % Lernbloecke
array[1..nB] of int: btask;
array[1..nB] of int: bfach;
array[1..nB] of int: bdur;
array[1..nB] of int: bdl;        % Deadline
int: puffer;
int: horizon;

array[1..nB] of var 1..nW: w;    % gewaehltes Fenster je Block
array[1..nB] of var 0..horizon: s;

% Block nur in freier Zeit oder in einem Lernbuero, das sein Fach anbietet
constraint forall(b in 1..nB)(not wlb[w[b]] \/ bfach[b] in wfaecher[w[b]]);
% In einer Lernbuero-Stunde wird nur ein Fach gelernt
constraint forall(b1, b2 in 1..nB where b1 < b2)((w[b1] = w[b2] /\ wlb[w[b1]]) -> bfach[b1] = bfach[b2]);
% Block liegt vollstaendig im Fenster
constraint forall(b in 1..nB)(s[b] >= wstart[w[b]] /\ s[b] + bdur[b] <= wend[w[b]]);
% Block endet mindestens 'puffer' vor der Deadline
constraint forall(b in 1..nB)(s[b] + bdur[b] <= bdl[b] - puffer);
% Keine Ueberschneidungen
constraint disjunctive(s, bdur);
% Symmetriebruch: gleich lange Bloecke derselben Aufgabe der Reihe nach
constraint forall(b in 1..nB-1 where btask[b] = btask[b+1])(s[b] <= s[b+1]);

% Ziel: Lernzeit gleichmaessig verteilen -> hoechste Tagesbelastung minimieren
array[0..6] of var 0..horizon: load;
constraint forall(d in 0..6)(load[d] = sum(b in 1..nB)(bdur[b] * bool2int(wday[w[b]] = d)));
var int: maxload = max(load);
solve minimize maxload;

output ["maxload=\(maxload)\n"];
