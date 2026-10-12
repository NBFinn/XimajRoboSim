; Lernbeispiel: Haltepunkt auf die Zeile $OUT[6]=TRUE setzen.
; F5 startet. Im Debugger ist count sichtbar, Ausgang 6 noch AUS.
; F5 setzt fort. WAIT wartet, bis du IN[3] in der E/A-Ansicht einschaltest.
DEF demo()
  DECL INT count=3
  $OUT[6]=TRUE
  WAIT FOR $IN[3]
  $OUT[6]=FALSE
END
