"""Etichette OdC valide per Risk Model — Literal, uno per RM supportato.

Generato da `prj/scripts/generate_odc_labels.py` a partire da `hierarchy_data.py`. NON MODIFICARE A
MANO: rieseguire lo script dopo ogni modifica alla gerarchia.
"""

from typing import Literal

type AMLOdC = Literal[
    "5069 - Adeguata verifica della clientela",
    "5070 - Conservazione e messa a disposizione dei documenti, dei dati e delle informazioni per il contrasto del riciclaggio e del finanziamento del terrorismo",
    "4712 - Obblighi di segnalazione e comunicazione",
    "5071 - Monitoraggio della movimentazione - Transaction Monitoring",
    "5072 - Limitazioni in materia di contante, titoli al portatore, intestazione prodotti di conto, moneta elettronica e libretti",
    "4714 - Gestione Antiterrorismo e embarghi",
    "5073 - Ruolo e Processi di Governo assegnati alla Funzione Antiriciclaggio",
    "5074 - Gestione del Management Information System",
]


type CreditoOdC = Literal[
    "5049 - Modelli di gestione del credito",
    "5050 - Attribuzione del rating",
    "4598 - Requisiti patrimoniali",
    "5047 - Rettifica di valore da valutazione analitico-statistica e da valutazione collettiva dei crediti in bonis",
    "4597 - Stress test",
    "5048 - Cessione e gestione portafogli / crediti",
    "4601 - Istruttoria e proposta",
    "4602 - Delibera",
    "4603 - Perfezionamento",
    "5088 - Fattori ESG nel processo di concessione",
    "4604 - Gestione e monitoraggio delle mitigazioni del rischio di credito",
    "4605 - Gestione delle perizie",
    "5051 - Monitoraggio del credito",
    "5052 - Intercettamento e gestione del credito anomalo",
    "4612 - Past due",
    "5053 - Unlikely to Pay",
    "5054 - Sofferenze",
]
