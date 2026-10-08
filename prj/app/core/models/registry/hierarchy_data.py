"""Dati statici gerarchia RM → MO → OdC e mapping codici per ambiente.

Fonte di verità unica: sostituisce `hierarchy.json` e `hierarchy_codes.json`.
Aggiornare questo file quando la gerarchia cambia, poi rieseguire
`prj/scripts/generate_odc_labels.py` per aggiornare `odc_labels.py`.
"""

from core.models.registry.hierarchy import MO, Hierarchy, OdC, RMHierarchy

# Mapping codice → per-ambiente (prod / non_prod) per RM, MO e OdC.
# `None` indica che l'entità non esiste nell'ambiente corrispondente.
HIERARCHY_CODES: dict[str, dict[str, dict[str, str | None]]] = {
    "mo": {
        "2503": {"non_prod": "2503", "prod": "2503"},
        "2576": {"non_prod": "2576", "prod": "2576"},
        "2578": {"non_prod": "2578", "prod": "2578"},
        "8833": {"non_prod": "8833", "prod": "8833"},
        "8834": {"non_prod": "8834", "prod": "8834"},
        "8835": {"non_prod": "8835", "prod": "8835"},
        "8838": {"non_prod": "8838", "prod": "8838"},
    },
    "odc": {
        "4597": {"non_prod": "4597", "prod": "4597"},
        "4598": {"non_prod": "4598", "prod": "4598"},
        "4601": {"non_prod": "4601", "prod": "4601"},
        "4602": {"non_prod": "4602", "prod": "4602"},
        "4603": {"non_prod": "4603", "prod": "4603"},
        "4604": {"non_prod": "4604", "prod": "4604"},
        "4605": {"non_prod": "4605", "prod": "4605"},
        "4612": {"non_prod": "4612", "prod": "4612"},
        "4712": {"non_prod": "4712", "prod": "4712"},
        "4714": {"non_prod": "4714", "prod": "4714"},
        "5047": {"non_prod": "5047", "prod": "5047"},
        "5048": {"non_prod": "5048", "prod": "5048"},
        "5049": {"non_prod": "5049", "prod": "5049"},
        "5050": {"non_prod": "5050", "prod": "5050"},
        "5051": {"non_prod": "5051", "prod": "5051"},
        "5052": {"non_prod": "5052", "prod": "5052"},
        "5053": {"non_prod": "5053", "prod": "5053"},
        "5054": {"non_prod": "5054", "prod": "5054"},
        "5069": {"non_prod": "5069", "prod": "5069"},
        "5070": {"non_prod": "5070", "prod": "5070"},
        "5071": {"non_prod": "5071", "prod": "5071"},
        "5072": {"non_prod": "5072", "prod": "5072"},
        "5073": {"non_prod": "5073", "prod": "5073"},
        "5074": {"non_prod": "5074", "prod": "5074"},
        "5088": {"non_prod": None, "prod": "5088"},
    },
    "rm": {
        "AML": {"non_prod": "1086", "prod": "1086"},
        "Credito": {"non_prod": "1080", "prod": "1080"},
    },
}


def build_hierarchy() -> Hierarchy:
    """Costruisce l'oggetto `Hierarchy` dai dati statici."""
    return Hierarchy(
        rms={
            "Credito": RMHierarchy(
                risk_model="Credito",
                mos=(
                    MO(
                        code="2503",
                        name="MO Rating",
                        description=(
                            "Il MO Rating copre il presidio del sistema di rating del rischio di credito lungo il suo"
                            " ciclo tecnico-operativo: dalla progettazione, utilizzo e monitoraggio dei modelli"
                            " quantitativi che misurano il rischio e stimano perdite attese, fino all'assegnazione"
                            " del rating al cliente e alle verifiche di tenuta delle valutazioni in condizioni"
                            " avverse. Rientrano quindi in questo ambito i controlli su data quality, coerenza"
                            " metodologica, procedure di controllo, ristima periodica delle griglie di"
                            " PD/LGD/EAD, calcolo della ECL e add-on IFRS 9, nonché l'adozione di modelli"
                            " dedicati a specifici canali distributivi. Sono inoltre comprese le attività di"
                            " attribuzione del rating, con attenzione alla correttezza dei dati di input, alla"
                            " tracciabilità documentale, alle casistiche di override, rating specialistici e stato"
                            ' "unrated", oltre ai profili trasversali di policy, procedure, applicativi IT,'
                            " assetto organizzativo e controlli di I e II livello. Il MO include anche i modelli"
                            " di stress test, limitatamente all'adeguatezza metodologica, alla corretta"
                            " applicazione delle stime, alla stima dei parametri e alla coerenza degli scenari e"
                            " delle eventuali azioni di recupero. Non copre invece la concessione del credito, il"
                            " monitoraggio del credito performing o non performing, la gestione di garanzie e"
                            " covenant, né il più ampio governo del rischio di credito, se non per gli aspetti"
                            " strettamente inerenti al sistema di rating."
                        ),
                        odcs=(
                            OdC(
                                code="5049",
                                name="Modelli di gestione del credito",
                                description=(
                                    "Riguarda il sistema di controllo a presidio degli aspetti quantitativi dei"
                                    " modelli di gestione del credito: progettazione, utilizzo e monitoraggio dei"
                                    " modelli che misurano il rischio di credito e stimano grandezze di rischio e"
                                    " perdite attese su crediti.\n"
                                    "- Presidi quantitativi: analisi di data quality; coerenza e adeguatezza"
                                    " metodologica; procedura di controllo.\n"
                                    "- Ristima periodica: processo di ristima delle griglie di PD, LGD e EAD.\n"
                                    "- IFRS9: processo di calcolo della ECL e definizione di add-on ai fini del"
                                    " principio IFRS9.\n"
                                    "- Modelli per canali distributivi: definizione e applicazione di modelli"
                                    " dedicati a specifici canali distributivi, inclusa la coerenza con i modelli"
                                    " già in essere.\n"
                                    "- Valutazioni trasversali, ove pertinenti e applicabili: policy e procedure;"
                                    " applicativi IT (vista utente); struttura organizzativa; controlli di I e II"
                                    " livello.\n"
                                    "Esclude: il processo di assegnazione del rating al cliente e le attività"
                                    " operative/documentali connesse, incluse attività di gestore / relationship"
                                    " manager o strutture centrali, alimentazione dei dati di input, raccolta e"
                                    " archiviazione documentale, rating specialistici, override e stato «unrated»"
                                    " (OdC «Attribuzione del rating»); le verifiche dei modelli di stress test su"
                                    " scenari sfavorevoli predefiniti, inclusa la corretta applicazione delle"
                                    " stime, la stima dei parametri e la coerenza degli scenari e delle eventuali"
                                    " azioni di recupero (OdC «Stress test»)."
                                ),
                            ),
                            OdC(
                                code="5050",
                                name="Attribuzione del rating",
                                description=(
                                    "Riguarda il processo di assegnazione del rating ai clienti, verificando che il"
                                    " rating attribuito sia coerente con i dati disponibili e con le regole del"
                                    " modello di valutazione.\n"
                                    "- Processo di assegnazione: attività in capo alle strutture di relazione"
                                    " (gestore / relationship manager) e, laddove previste, alle strutture"
                                    " centrali.\n"
                                    "- Dati e tracciabilità: corretta alimentazione dei dati di input al modello,"
                                    " manuali o automatici; raccolta e archiviazione della relativa"
                                    " documentazione.\n"
                                    "- Casistiche specifiche: rating specialistici; override; attribuzione dello"
                                    " stato «unrated».\n"
                                    "- Valutazioni trasversali, ove pertinenti e applicabili: policy e procedure;"
                                    " applicativi IT (vista utente); struttura organizzativa; controlli di I e II"
                                    " livello.\n"
                                    "Esclude: la progettazione, l'utilizzo e il monitoraggio dei modelli di"
                                    " misurazione del rischio di credito e di stima delle perdite attese su"
                                    " crediti, inclusi data quality, adeguatezza metodologica del sistema di"
                                    " controllo quantitativo, ristima di PD/LGD/EAD, calcolo della ECL, add-on"
                                    " IFRS9 e modelli per specifici canali distributivi (OdC «Modelli di gestione"
                                    " del credito»); le verifiche di tenuta delle valutazioni in condizioni avverse"
                                    " e di risposta a scenari sfavorevoli predefiniti proprie dei modelli di stress"
                                    " test (OdC «Stress test»)."
                                ),
                            ),
                        ),
                    ),
                    MO(
                        code="2576",
                        name="MO Gestione e controllo del rischio di credito",
                        description=(
                            "Il Macro Obiettivo copre i presidi con cui la banca misura e controlla gli effetti del"
                            " rischio di credito sulla solidità patrimoniale e sulla valutazione dei crediti in"
                            " bonis. Rientrano quindi i processi, le metodologie, i modelli, gli strumenti e i"
                            " controlli utilizzati per: determinare correttamente il requisito patrimoniale"
                            " dell'organizzazione; calcolare in modo completo e coerente le rettifiche di valore"
                            " sui crediti performing, sia tramite valutazioni analitico-statistiche sia collettive;"
                            " gestire i relativi impatti contabili, inclusi quelli IFRS 9 sui crediti in bonis al"
                            " fair value. L'ambito comprende anche gli assetti trasversali di supporto, ove"
                            " pertinenti: policy e procedure, applicativi IT in vista utente, struttura"
                            " organizzativa e controlli di primo e secondo livello.\n\n"
                            "Per il tagging documentale, questo MO intercetta contenuti su calcolo del requisito"
                            " patrimoniale, metodologie di quantificazione, modelli di impairment/ECL su crediti"
                            " in bonis, riserva collettiva, corretto perimetro applicativo delle rettifiche e"
                            " sistema dei controlli che presidia tali processi.\n\n"
                            "Non rientrano invece l'attribuzione del rating, la concessione del credito, le"
                            " garanzie e i covenant, il monitoraggio del credito performing e la gestione del"
                            " credito non performing come ambiti autonomi. In particolare, il MO non copre la"
                            " gestione delle posizioni deteriorate o da stralciare, salvo i richiami necessari a"
                            " delimitare il perimetro delle rettifiche; né copre la valutazione contabile del"
                            " credito quando il focus è diverso dal calcolo delle rettifiche sui crediti in bonis"
                            " o dal requisito patrimoniale."
                        ),
                        odcs=(
                            OdC(
                                code="4598",
                                name="Requisiti patrimoniali",
                                description=(
                                    "Riguarda la determinazione dei requisiti patrimoniali dell'organizzazione,"
                                    " verificando che il patrimonio e il requisito patrimoniale siano determinati"
                                    " in modo corretto, completo e coerente con le regole applicabili.\n"
                                    "- Presidi del processo: sistema di controllo a presidio dei processi che"
                                    " concorrono alla determinazione dei requisiti patrimoniali.\n"
                                    "- Metodologie e strumenti: metodologie e strumenti utilizzati per il calcolo"
                                    " del requisito patrimoniale.\n"
                                    "- Assetti trasversali di supporto (ove pertinenti e applicabili): policy e"
                                    " procedure, applicativi IT (vista utente), struttura organizzativa, controlli"
                                    " di I e II livello.\n"
                                    "Esclude: la determinazione delle rettifiche di valore sui crediti in bonis,"
                                    " incluse valutazioni analitico-statistiche o collettive, modelli di rettifica,"
                                    " riserva collettiva, impatti IFRS 9 e verifiche su posizioni"
                                    " deteriorate/da stralciare, che rientrano in «Rettifica di valore da"
                                    " valutazione analitico-statistica e da valutazione collettiva dei crediti in"
                                    " bonis». Anche se tali componenti possono avere impatti patrimoniali, qui"
                                    " l'ambito è il calcolo del requisito patrimoniale e i relativi presidi, non"
                                    " la valutazione contabile del credito."
                                ),
                            ),
                            OdC(
                                code="5047",
                                name="Rettifica di valore da valutazione analitico-statistica e da valutazione collettiva dei crediti in bonis",
                                description=(
                                    "Riguarda la determinazione delle rettifiche di valore sui crediti in bonis,"
                                    " con focus sulle valutazioni analitico-statistiche e collettive, sui modelli"
                                    " utilizzati e sulla corretta determinazione delle rettifiche applicate.\n"
                                    "- Valutazioni dei crediti in bonis: valutazioni analitico-statistiche e"
                                    " valutazioni collettive per determinare le rettifiche di valore.\n"
                                    "- Modelli e quantificazione: verifiche sui modelli e sulla determinazione"
                                    " delle rettifiche applicate; riserva collettiva sui crediti in bonis.\n"
                                    "- Corretto perimetro applicativo: corretta applicazione della normativa"
                                    " inerente l'applicazione di rettifiche forfettarie sui crediti deteriorati;"
                                    " esclusione di posizioni deteriorate azzerate/da stralciare.\n"
                                    "- Impatti contabili: impatti IFRS 9 sulla valutazione dei crediti in bonis al"
                                    " fair value.\n"
                                    "- Assetti trasversali di supporto (ove pertinenti e applicabili): policy e"
                                    " procedure, applicativi IT (vista utente), struttura organizzativa, controlli"
                                    " di I e II livello.\n"
                                    "Esclude: la determinazione dei requisiti patrimoniali dell'organizzazione e il"
                                    " sistema di controllo sui processi che concorrono al calcolo del requisito"
                                    " patrimoniale, incluse metodologie e strumenti di calcolo del requisito"
                                    " patrimoniale, che rientrano in «Requisiti patrimoniali». Qui l'ambito è la"
                                    " valutazione/rrettifica del credito in bonis, non la quantificazione della"
                                    " solidità patrimoniale complessiva."
                                ),
                            ),
                            OdC(
                                code="4597",
                                name="Stress test",
                                description=(
                                    "Riguarda le verifiche sui modelli di stress test per valutare la solidità"
                                    " delle valutazioni in condizioni avverse e la risposta del sistema o del"
                                    " processo a scenari sfavorevoli predefiniti.\n"
                                    "- Metodologia: adeguatezza metodologica dei modelli di stress test.\n"
                                    "- Stime e parametri: corretta applicazione delle stime; correttezza della"
                                    " stima dei parametri.\n"
                                    "- Scenari: coerenza degli scenari e delle eventuali azioni di recupero.\n"
                                    "- Valutazioni trasversali, ove pertinenti e applicabili: policy e procedure;"
                                    " applicativi IT (vista utente); struttura organizzativa; controlli di I e II"
                                    " livello.\n"
                                    "Esclude: il processo di assegnazione del rating al cliente e le relative"
                                    " attività di strutture di relazione / strutture centrali, alimentazione dei"
                                    " dati di input, documentazione, rating specialistici, override e stato"
                                    " «unrated» (OdC «Attribuzione del rating»); il sistema di controllo a"
                                    " presidio degli aspetti quantitativi dei modelli di gestione del credito,"
                                    " inclusi data quality, coerenza e adeguatezza metodologica dei modelli di"
                                    " rischio di credito, ristima delle griglie di PD/LGD/EAD, calcolo della ECL,"
                                    " add-on IFRS9 e modelli dedicati a specifici canali distributivi (OdC"
                                    " «Modelli di gestione del credito»)."
                                ),
                            ),
                            OdC(
                                code="5048",
                                name="Cessione e gestione portafogli / crediti",
                                description=(
                                    "Riguarda i processi di cessione e di successiva gestione di portafogli di"
                                    " crediti e di singoli crediti, nonché la gestione delle operazioni di Credit"
                                    " Risk Transfer.\n"
                                    "- Cessione: processo di cessione di portafogli; processo di cessione di"
                                    " singoli crediti.\n"
                                    "- Gestione post-cessione: processo di gestione di portafogli ceduti o di"
                                    " crediti ceduti.\n"
                                    "- Operazioni strutturate: processo di gestione delle operazioni di Credit"
                                    " Risk Transfer.\n"
                                    "Esclude: la classificazione, il monitoraggio e il trattamento dello stato di"
                                    " rischio delle posizioni in «Past due», «Unlikely to Pay» e «Sofferenze»; a"
                                    " differenza di «Past due» non riguarda probation period, trascinamenti o past"
                                    " due tecnici, a differenza di «Unlikely to Pay» non riguarda rettifiche,"
                                    " cure period o Add-on su posizioni UTP, e a differenza di «Sofferenze» non"
                                    " riguarda passaggio a sofferenza, valutazione analitica specifica, attività"
                                    " di recupero, gestione contabile della posizione, incassi, GBV, spese o"
                                    " stralci della singola posizione classificata a sofferenza."
                                ),
                            ),
                        ),
                    ),
                    MO(
                        code="2578",
                        name="MO Concessione del credito",
                        description=(
                            "Il Macro Obiettivo copre il processo end-to-end di concessione del credito verso"
                            " clientela bonis, inclusa quella a Proattivo, sia ordinaria sia istituzionale, nelle"
                            " diverse strutture del Gruppo, dalla costruzione della proposta fino alla sua messa a"
                            " terra operativa. Rientrano nell'ambito i presidi, anche organizzativi, procedurali,"
                            " applicativi e di controllo di I e II livello, relativi a: istruttoria e proposta di"
                            " affidamento, con verifiche anagrafiche, documentali, tecniche, legali e"
                            " specialistiche, valutazione del merito creditizio e della coerenza complessiva"
                            " dell'operazione; fase deliberativa, con riesame dell'istruttoria, assunzione e"
                            " formalizzazione della decisione, verifica di competenze, limiti, vincoli normativi,"
                            " pareri e clearing; fase di perfezionamento, con contrattualizzazione, registrazione"
                            " nei sistemi, ripartizione dei fidi, erogazione e ulteriori adempimenti esecutivi."
                            " Il MO include inoltre, in modo trasversale a tali fasi, i controlli specificamente"
                            " riferiti ai fattori ESG e reputazionali quando incidono sul processo di concessione,"
                            " inclusi documentazione, classificazioni, clearing e verifiche dedicate.\n\n"
                            "Non rientrano invece nell'ambito il monitoraggio successivo del credito performing,"
                            " la gestione del credito non performing, il governo complessivo del rischio di"
                            " credito, la gestione autonoma di garanzie e covenant al di fuori del loro esame nel"
                            " processo concessorio, né i sistemi/modelli di rating come ambito specialistico"
                            ' separato. In sintesi, il MO presidia il "decidere e rendere operativo" un'
                            " affidamento, non la gestione successiva della relazione creditizia."
                        ),
                        odcs=(
                            OdC(
                                code="4601",
                                name="Istruttoria e proposta",
                                description=(
                                    "Riguarda la fase di costruzione e valutazione della proposta di affidamento"
                                    " prima della decisione, includendo le verifiche istruttorie, tecniche e legali"
                                    " necessarie a formulare la proposta; non copre l'assunzione della delibera né"
                                    " l'esecuzione/perfezionamento. Presidi trasversali, ove pertinenti: policy e"
                                    " procedure, applicativi IT (vista utente), struttura organizzativa, controlli"
                                    " di I e II livello. Attività preliminari di istruttoria: gestione delle"
                                    " anagrafiche; segmentazione regolamentare; gruppi economici. Istruttoria"
                                    " creditizia: correttezza formale e sostanziale del processo istruttorio;"
                                    " completezza della documentazione; valutazione del merito creditizio; analisi"
                                    " dei dati di bilancio e delle evidenze da fonti informative esterne; coerenza"
                                    " della proposta rispetto all'Andamento Settoriale; strutturazione delle"
                                    " operazioni di Finanza Strutturata; analisi del rischio complessivo del Gruppo"
                                    " Economico su Gruppo Bancario; cauzionalità degli eventuali garanti; coerenza"
                                    " complessiva della proposta di fido; calcolo della competenza deliberativa ai"
                                    " fini della proposta; analisi dei debitori deduti nel factoring; modifiche"
                                    " contrattuali su operazioni già in essere (ristrutturazioni, accolli,"
                                    " rinegoziazioni, revisione covenant, revisione condizioni economiche);"
                                    " valutazione del profilo di rischio / rendimento. Istruttoria tecnica, legale"
                                    " e valutazioni specialistiche: valutazione tecnica del bene/progetto da"
                                    " finanziare (finanziamenti ipotecari, project financing, progetti Research and"
                                    " Development, leasing); rilascio di pareri di procedibilità; predisposizione"
                                    " di schemi contrattuali di finanziamento; identificazione di misure di"
                                    " forbearance e simulazione NPV; valutazione CRA; valutazione del Leveraged"
                                    " Transaction, inclusa targatura; valutazione del flag POCI; acquisto di"
                                    " portafogli in bonis; esecuzione dello SPPI test; targatura SIPF; adempimento"
                                    " degli obblighi normativi; acquisizione dei pareri / clearing previsti."
                                    " Perimetro: tutte le tipologie di affidamento nelle varie strutture di"
                                    " Gruppo, su clientela ordinaria e istituzionale, e tutti gli stati gestionali"
                                    " della clientela Bonis, inclusa la clientela a Proattivo. Esclude: a"
                                    " differenza di «Delibera», non riguarda la decisione dell'organo competente,"
                                    " il rispetto di RAF/plafond/massimali/lending limit, la formalizzazione della"
                                    " delibera/certificazione, il Parere di Conformità, la quota di final take"
                                    " massima sottoscrivibile (HTC) o la certificazione SPPI del deliberante; a"
                                    " differenza di «Perfezionamento», non riguarda il perfezionamento sui"
                                    " sistemi, la stipula contrattuale, l'erogazione, il TEG, la sindacazione, la"
                                    " scheda prodotto o i flussi operativi/contabili post-delibera; a differenza"
                                    " di «Fattori ESG nel processo di concessione», non riguarda le valutazioni"
                                    " ESG/reputazionali, ESG Score, Net Zero, tassonomia europea, categorie o"
                                    " attributi di sostenibilità, EPC mutui o Equator Principles."
                                ),
                            ),
                            OdC(
                                code="4602",
                                name="Delibera",
                                description=(
                                    "Riguarda la fase decisionale della concessione creditizia, cioè il riesame"
                                    " dell'istruttoria già svolta e l'assunzione/formalizzazione della decisione"
                                    " da parte del deliberante; non copre né la formazione del fascicolo"
                                    " istruttorio né il perfezionamento operativo successivo. Presidi trasversali,"
                                    " ove pertinenti: policy e procedure, applicativi IT (vista utente), struttura"
                                    " organizzativa, controlli di I e II livello. Assunzione della decisione"
                                    " creditizia: esame dell'istruttoria; calcolo e rispetto della competenza"
                                    " deliberativa; processo di rinnovo automatico dei fidi; coerenza tra indirizzi"
                                    " gestionali e concessione creditizia; acquisizione del Parere di Conformità."
                                    " Limiti e vincoli: rispetto dei limiti massimi consentiti di Risk Appetite"
                                    " Framework (RAF), plafond, massimali di affidabilità, lending limit per i"
                                    " Grandi Rischi individuali; rispetto di specifici vincoli normativi. Pareri,"
                                    " clearing e formalizzazione: avvenuto rilascio dei pareri / clearing previsti"
                                    " e coerenza della delibera con il loro contenuto; formalizzazione della"
                                    " delibera/certificazione; rispetto delle facoltà deliberative in caso di"
                                    " reiterazioni, inclusa la concessione di misure di forbearance. Casistiche"
                                    " specialistiche oggetto di decisione: valutazione della sussistenza dei"
                                    " requisiti per la targatura delle misure di forbearance; coerenza della"
                                    " simulazione del NPV della nuova misura di forbearance con l'operazione"
                                    " effettivamente in proposta; Leveraged Transactions; flag POCI; delibera"
                                    " della quota di final take massima sottoscrivibile (HTC); SPPI test"
                                    " limitatamente all'attività di certificazione e controllo del deliberante."
                                    " Perimetro: tutte le tipologie di affidamento nelle varie strutture di"
                                    " Gruppo, su clientela ordinaria e istituzionale, e tutti gli stati gestionali"
                                    " della clientela Bonis, inclusa la clientela a Proattivo. Esclude: a"
                                    " differenza di «Istruttoria e proposta», non riguarda la raccolta e"
                                    " valutazione di anagrafiche, bilanci, fonti esterne, merito creditizio,"
                                    " gruppi economici, CRA, SIPF, acquisto di portafogli in bonis, esecuzione"
                                    " dello SPPI test, valutazioni tecniche/legali o la predisposizione degli"
                                    " schemi contrattuali; a differenza di «Perfezionamento», non riguarda il"
                                    " perfezionamento della delibera sui sistemi, la stipula, l'erogazione, il"
                                    " TEG, la sindacazione, la scheda prodotto o la gestione operativa del delta"
                                    " NPV/catch up adjustment; a differenza di «Fattori ESG nel processo di"
                                    " concessione», non riguarda le autorizzazioni e i clearing motivati da output"
                                    " ESG/reputazionali, il RAF in chiave ESG, le categorie di sostenibilità o"
                                    " Equator Principles."
                                ),
                            ),
                            OdC(
                                code="4603",
                                name="Perfezionamento",
                                description=(
                                    "Riguarda la fase successiva alla delibera in cui l'affidamento viene"
                                    " perfezionato, contrattualizzato, registrato nei sistemi ed eventualmente"
                                    " erogato; non copre né l'istruttoria/proposta né la decisione deliberativa."
                                    " Presidi trasversali, ove pertinenti: policy e procedure, applicativi IT"
                                    " (vista utente), struttura organizzativa, controlli di I e II livello."
                                    " Perfezionamento del fido e messa a terra della delibera: completezza"
                                    " documentale e contrattuale; perfezionamento della delibera sui sistemi"
                                    " gestionali; ripartizione dei fidi; perfezionamento e stipula dei contratti;"
                                    " rispetto delle condizioni di delibera. Erogazione e presidi operativi:"
                                    " erogazione dei finanziamenti, incluse le erogazioni in Stato Avanzamento"
                                    " Lavori (SAL); correttezza del Tasso Effettivo Globale (TEG); presidio del"
                                    " rischio di Sindacazione; predisposizione della scheda prodotto; invio alle"
                                    " strutture competenti di Capogruppo della scheda prodotto per operazioni di"
                                    " securitisation. Misure di forbearance nella fase esecutiva: corretta"
                                    " targatura delle misure di forbearance; monitoraggio dei disallineamenti tra"
                                    " linee identificate e linee effettivamente targate; gestione del delta NPV e"
                                    " flusso dati con Motore Forborne per l'eventuale riclassificazione della"
                                    " controparte a deteriorato, solo per clienti in bonis; calcolo del catch up"
                                    " adjustment tramite dialogo con Motore NPV e comunicazione del dato alla"
                                    " contabilità. Perimetro: tutte le tipologie di affidamento nelle varie"
                                    " strutture di Gruppo, su clientela ordinaria e istituzionale, e tutti gli"
                                    " stati gestionali della clientela Bonis, inclusa la clientela a Proattivo."
                                    " Esclude: a differenza di «Istruttoria e proposta», non riguarda la"
                                    " costruzione della proposta, il merito creditizio, le analisi di bilancio e"
                                    " fonti esterne, le valutazioni tecniche/legali, la predisposizione degli"
                                    " schemi contrattuali o l'identificazione iniziale della forbearance con"
                                    " relativa simulazione NPV; a differenza di «Delibera», non riguarda la"
                                    " decisione dell'organo competente, il rispetto della competenza/facoltà"
                                    " deliberativa, RAF/plafond/massimali/lending limit, il Parere di Conformità"
                                    " o la formalizzazione della delibera/certificazione; a differenza di «Fattori"
                                    " ESG nel processo di concessione», non riguarda la documentazione ESG"
                                    " specifica di perfezionamento, l'EPC mutui, il parere di clearing ESG o la"
                                    " verifica della destinazione dei fondi rispetto alla categoria di"
                                    " sostenibilità."
                                ),
                            ),
                            OdC(
                                code="5088",
                                name="Fattori ESG nel processo di concessione",
                                description=(
                                    "Riguarda esclusivamente i controlli sui Fattori ESG nel processo di"
                                    " concessione, in modo trasversale a istruttoria e proposta, delibera e"
                                    " perfezionamento; intercetta quindi solo i contenuti in cui il focus è su"
                                    " sostenibilità, rischi ESG/reputazionali, categorie di sostenibilità e"
                                    " relativi clearing/documenti. Presidi trasversali, ove pertinenti: policy e"
                                    " procedure, applicativi IT (vista utente), struttura organizzativa, controlli"
                                    " di I e II livello. Istruttoria e proposta lato ESG: gestione dei dati"
                                    " settoriali nelle anagrafiche; valutazione dell'operazione e della"
                                    " controparte lato ESG, incluse operazioni di finanza strutturata, prodotti"
                                    " creditizi a catalogo e operazioni tailor made; raccolta, verifica della"
                                    " completezza e archiviazione della documentazione a supporto delle"
                                    " caratteristiche di sostenibilità dell'operazione e della controparte,"
                                    " inclusi i piani di transizione; valutazione dell'impatto sociale ove"
                                    " previsto; correttezza formale e sostanziale del processo istruttorio per i"
                                    " profili ESG; valutazione degli Equator Principles per le operazioni di"
                                    " Finanza Strutturata / Structured Deals; clearing di primo livello tramite"
                                    " questionario ESG/reputazionale; verifica di ESG Sectoral Color Coding,"
                                    " fascia di indirizzamento in base all'ESG Score e corretto instradamento nel"
                                    " processo di concessione (Standard, Clearing di II livello, II livello +"
                                    " transition plan); verifica degli impatti sui target Net Zero; assegnazione"
                                    " di una categoria di sostenibilità e validazione dell'attributo di"
                                    " sostenibilità nei casi previsti; adempimento degli obblighi normativi e"
                                    " acquisizione dei pareri / clearing previsti, incluso ESG & Reputational"
                                    " Clearing ove previsto; coerenza degli impegni dichiarati dal cliente"
                                    " rispetto alla finalità del finanziamento; analisi dell'iter di verifica dei"
                                    " criteri di allineamento alla tassonomia europea. Delibera lato ESG:"
                                    " integrazione delle verifiche ordinarie di istruttoria rispetto ai fattori"
                                    " ESG; autorizzazione degli organi competenti in funzione degli output delle"
                                    " determinazioni ESG; analisi ESG con riferimento al RAF; rispetto di"
                                    " specifici vincoli normativi; rispetto degli Equator Principles; avvenuto"
                                    " rilascio dei pareri / clearing previsti e coerenza della delibera con il"
                                    " loro contenuto. Perfezionamento lato ESG: completezza della documentazione"
                                    " peculiare per gli aspetti ESG di perfezionamento della pratica, inclusi EPC"
                                    " mutui e parere di clearing quando previsti; verifica della coerente"
                                    " destinazione dei fondi in funzione della categoria di sostenibilità"
                                    " assegnata. Esclude: il processo ordinario di «Istruttoria e proposta»,"
                                    " «Delibera» e «Perfezionamento» quando il contenuto non è riferito a fattori"
                                    " ESG/reputazionali; quindi non riguarda, se privi di focus ESG, merito"
                                    " creditizio, analisi di bilancio, competenza deliberativa generale, TEG,"
                                    " sindacazione, stipula/erogazione o altri adempimenti ordinari di concessione"
                                    " del credito."
                                ),
                            ),
                        ),
                    ),
                    MO(
                        code="8833",
                        name="MO Credit Risk Mitigation (Garanzie e Covenant)",
                        description=(
                            "Il MO «Credit Risk Mitigation (Garanzie e Covenant)» copre i presidi relativi alle"
                            " tecniche di mitigazione del rischio di credito dopo la fase decisionale del credito,"
                            " con focus su garanzie, covenant e perizie. Rientrano in questo ambito la gestione"
                            " operativa delle garanzie lungo il loro ciclo di vita (acquisizione, perfezionamento,"
                            " censimento a sistema, variazioni dell'importo garantito, rinnovi e liberazioni), il"
                            " controllo della loro corretta materialità e documentazione, il monitoraggio di"
                            " anomalie e disallineamenti, nonché l'aggiornamento periodico delle garanzie reali ai"
                            " fini della qualità del dato e della loro eventuale eleggibilità regolamentare. Il MO"
                            " include inoltre la verifica di coerenza tra quanto deliberato e quanto acquisito, i"
                            " flussi documentali collegati alle posizioni deteriorate limitatamente agli aspetti di"
                            " garanzie/documentazione, e il censimento e monitoraggio dei covenant tramite"
                            " applicativi dedicati.\n\n"
                            "Nello stesso perimetro rientra la gestione delle perizie, intesa come verifica della"
                            " rispondenza ai requisiti BCE/ABI, presidio dell'operato di periti e provider,"
                            " controllo della rotazione e verifica della documentazione peritale.\n\n"
                            "Non rientrano invece in questo MO le fasi di istruttoria, proposta e delibera del"
                            " credito, né il monitoraggio complessivo delle esposizioni performing o non"
                            " performing, salvo gli aspetti strettamente connessi all'aggiornamento delle garanzie"
                            " e al trasferimento documentale. Non copre inoltre rating o concessione del credito"
                            " se non per la coerenza tra delibera e mitiganti acquisiti."
                        ),
                        odcs=(
                            OdC(
                                code="4604",
                                name="Gestione e monitoraggio delle mitigazioni del rischio di credito",
                                description=(
                                    "Ambito: copre la gestione operativa, il monitoraggio e l'aggiornamento delle"
                                    " mitigazioni del rischio di credito riferite a garanzie e covenant, incluse le"
                                    " verifiche su acquisizione, perfezionamento e censimento a sistema delle"
                                    " garanzie; non riguarda le fasi di istruttoria e proposta e di delibera.\n"
                                    "- Garanzie - acquisizione e gestione: acquisizione, perfezionamento e"
                                    " censimento a sistema delle garanzie; gestione delle variazioni in aumento e"
                                    " in diminuzione dell'importo garantito, rinnovi e liberazione delle garanzie.\n"
                                    "- Materialità e anomalie: gestione della materialità delle garanzie, inclusa"
                                    " custodia degli originali della documentazione e quadrature periodiche;"
                                    " monitoraggio di garanzie non perfezionate, garanzie prive di affidamento"
                                    " associato e segnalazioni ai garanti.\n"
                                    "- Garanzie reali - aggiornamento e qualità: aggiornamento periodico dei dati"
                                    " relativi alle garanzie reali, anche ai fini della verifica della loro"
                                    " eleggibilità regolamentare; aggiornamento delle garanzie relative a posizioni"
                                    " classificate a credito Proattivo, Past Due, UTP e Sofferenza; verifica"
                                    " periodica della qualità delle garanzie e dei garanti.\n"
                                    "- Sofferenze e data quality: ricezione della documentazione e delle garanzie"
                                    " dalla rete commerciale; trasferimento della documentazione e delle garanzie"
                                    " alle Strutture dedicate al recupero crediti; presidi collegati a Scheda"
                                    " Documentale e Data Quality.\n"
                                    "- Coerenza e covenant: verifica della coerenza tra le macro tipologie di"
                                    " garanzia indicate in delibera e il cluster di garanzia acquisito, nonché con"
                                    " il valore del sottostante ove previsto; censimento a sistema e monitoraggio"
                                    " dei covenant tramite applicativo dedicato.\n"
                                    "Esclude: a differenza di «Gestione delle perizie», non riguarda la"
                                    " rispondenza delle perizie ai requisiti BCE/ABI, il monitoraggio delle"
                                    " attività dei periti/provider, la rotazione dei periti o la verifica della"
                                    " documentazione peritale."
                                ),
                            ),
                            OdC(
                                code="4605",
                                name="Gestione delle perizie",
                                description=(
                                    "Ambito: copre la gestione delle perizie, con focus sui requisiti della perizia"
                                    " e sul presidio di periti/provider; non riguarda la gestione operativa e il"
                                    " monitoraggio di garanzie e covenant, né le fasi di istruttoria e proposta,"
                                    " di delibera e di perfezionamento.\n"
                                    "- Requisiti della perizia: verifica della rispondenza delle perizie ai"
                                    " requisiti definiti dalla BCE e dall'ABI.\n"
                                    "- Presidio periti/provider: monitoraggio delle attività dei periti e dei"
                                    " provider; verifica della rotazione dei periti.\n"
                                    "- Documentazione peritale: verifica della documentazione peritale.\n"
                                    "Esclude: a differenza di «Gestione e monitoraggio delle mitigazioni del"
                                    " rischio di credito», non riguarda acquisizione, perfezionamento e censimento"
                                    " a sistema delle garanzie, gestione delle variazioni in aumento/diminuzione"
                                    " dell'importo garantito, rinnovi o liberazione, gestione della materialità"
                                    " delle garanzie, monitoraggio di garanzie non perfezionate o prive di"
                                    " affidamento associato, aggiornamento periodico delle garanzie reali ed"
                                    " eleggibilità regolamentare, attività sulle sofferenze, verifica di coerenza"
                                    " tra macro tipologie di garanzia e cluster acquisito, né censimento e"
                                    " monitoraggio dei covenant."
                                ),
                            ),
                        ),
                    ),
                    MO(
                        code="8834",
                        name="MO Gestione e monitoraggio del credito performing",
                        description=(
                            "Questo Macro Obiettivo presidia il ciclo di gestione del credito successivo alla"
                            " concessione, con focus sulle esposizioni ancora performing, anche quando presentano"
                            " segnali precoci di deterioramento. L'ambito comprende sia il monitoraggio ordinario"
                            " degli affidamenti e del portafoglio sia l'intercettamento e la gestione proattiva"
                            " del credito anomalo prima del passaggio al non performing. Rientrano quindi il"
                            " controllo dell'andamento delle linee in essere, degli utilizzi, dei fidi scaduti e"
                            " dei rinnovi, delle classificazioni e dello staging IFRS9, delle migrazioni di"
                            " portafoglio, delle posizioni Forborne performing e dei relativi piani di rientro,"
                            " nonché il presidio di specifici comparti o operazioni rilevanti ai fini del"
                            " monitoraggio del costo del credito. Il MO copre anche l'intero perimetro Early"
                            " Warning: da un lato l'analisi delle posizioni intercettate e dei segnali di"
                            " attenzione, dall'altro i motori EWS e i relativi trigger, inclusi qualità dei dati,"
                            " adeguatezza metodologica, controlli ed efficacia predittiva, in funzione della"
                            " gestione attiva delle controparti attenzionate, comprese quelle in stage 2 o nello"
                            " stage gestionale 1PS. Non rientrano invece in questo MO la concessione del credito,"
                            " la definizione del rating, la gestione delle garanzie e dei covenant, né la gestione"
                            " del credito già classificato non performing. In sintesi, il perimetro è quello del"
                            " presidio operativo e gestionale del credito performing e delle anomalie iniziali che"
                            " lo interessano."
                        ),
                        odcs=(
                            OdC(
                                code="5051",
                                name="Monitoraggio del credito",
                                description=(
                                    "Ambito: presidia il monitoraggio del credito su affidamenti in essere e"
                                    " portafoglio, verificando andamento delle linee, segnali di attenzione,"
                                    " classificazioni/staging, rinnovi e specifici presidi su Forborne e altri"
                                    " comparti.\n"
                                    "- Fidi in essere: modalità di utilizzo delle linee di credito in essere;"
                                    " rotazione delle linee commerciali; elasticità degli utilizzi di cassa;"
                                    " destinazione dei finanziamenti mlt; analisi dei fidi scaduti; utilizzi su"
                                    " linee di credito transitorie scadute; tempestività nel rinnovo degli"
                                    " affidamenti.\n"
                                    "- Segnali di monitoraggio: analisi delle posizioni intercettate da EWS;"
                                    " verifica dei disallineamenti tra SAB e SAG.\n"
                                    "- Portafoglio e andamento: analisi della distribuzione degli impieghi per"
                                    " rating, staging IFRS9, segmento regolamentare e attività economica;"
                                    " incidenza e andamento nel tempo delle esposizioni Forborne; tassi di"
                                    " migrazione verso bonis e verso deteriorato; monitoraggio andamentale di"
                                    " affidamenti su clientela ordinaria e istituzionale, incluse linee «ordinarie»"
                                    " a breve e medio lungo termine, finanza strutturata, securitisation e"
                                    " operazioni per l'acquisto di strumenti finanziari; monitoraggio finalizzato"
                                    " a prevenire o ridurre criticità, incluse quelle ai sensi del principio"
                                    " IFRS9.\n"
                                    "- Staging e rinnovi: processo di override staging; motore di staging; rinnovo"
                                    " dei fidi previa acquisizione dei pareri e dei clearing previsti.\n"
                                    "- Forborne e piani di rientro: monitoraggio delle posizioni forborne"
                                    " «performing» e «performing da non performing»; corretto calcolo del probation"
                                    " period per l'uscita dal forborne dopo 24 mesi; rispetto dei requisiti per il"
                                    " ritorno in non-performing delle posizioni «performing da non performing»;"
                                    " identificazione delle errate targature; rispetto di tempi e rimborsi"
                                    " formalizzati nei piani di rientro.\n"
                                    "- Ambiti specifici: operazioni classificate come Leveraged Transactions;"
                                    " monitoraggio delle quote HTC; gestione dell'invenduto HTCS; processo di"
                                    " monitoraggio del costo del credito.\n"
                                    "Esclude: a differenza di «Intercettamento e gestione del credito anomalo»,"
                                    " non riguarda il processo di intercettamento e gestione proattiva del credito"
                                    " anomalo per segmenti/clientela, la coerenza delle strategie gestionali"
                                    " rispetto all'Andamento Settoriale, la gestione attiva delle controparti a"
                                    " stage 2 e nello stage gestionale 1PS, né la verifica metodologica e di"
                                    " controllo dei motori EWS (data quality, adeguatezza metodologica, efficacia"
                                    " e predittività); per EWS, qui rileva l'analisi delle posizioni intercettate,"
                                    " non la governance del modello."
                                ),
                            ),
                            OdC(
                                code="5052",
                                name="Intercettamento e gestione del credito anomalo",
                                description=(
                                    "Ambito: presidia la fase di intercettamento e gestione proattiva del credito"
                                    " anomalo, comprese le strategie gestionali sulle posizioni intercettate e i"
                                    " modelli/sistemi di intercettamento.\n"
                                    "- Processo di gestione proattiva: verifica della gestione delle posizioni"
                                    " privati Retail, SME Retail, Corporate e Financial Institutions; coerenza"
                                    " delle strategie gestionali in relazione all'Andamento Settoriale.\n"
                                    "- Controparti attenzionate: rispetto dei processi di gestione attiva delle"
                                    " controparti a stage 2 ai sensi del principio IFRS9 e delle controparti nello"
                                    " stage gestionale 1PS.\n"
                                    "- Modelli di intercettamento: motori EWS e relativi triggers events, con"
                                    " verifica di data quality, coerenza e adeguatezza metodologica, procedure di"
                                    " controllo e processo di periodico aggiornamento sull'efficacia e la"
                                    " predittività dei sistemi di Early Warning System.\n"
                                    "Esclude: a differenza di «Monitoraggio del credito», non riguarda il"
                                    " monitoraggio ordinario dei fidi in essere e del portafoglio né i relativi"
                                    " esiti operativi: utilizzo linee, fidi scaduti, disallineamenti SAB-SAG,"
                                    " distribuzioni di portafoglio per rating/staging IFRS9/segmento"
                                    " regolamentare/attività economica, migrazioni bonis-deteriorato, override o"
                                    " motore di staging, rinnovo fidi, monitoraggio Forborne «performing», piani di"
                                    " rientro, Leveraged Transactions, HTC/HTCS e costo del credito; per EWS, qui"
                                    " rilevano il modello e il processo di intercettamento, non il solo esame delle"
                                    " posizioni intercettate."
                                ),
                            ),
                        ),
                    ),
                    MO(
                        code="8835",
                        name="MO Credito non performing",
                        description=(
                            'Il MO "Credito non performing" presidia l\'intero perimetro di gestione e controllo'
                            " delle esposizioni creditizie deteriorate, lungo tutto il loro ciclo di vita: dalla"
                            " fase di scaduto/Past Due, alla classificazione a Unlikely to Pay/Inadempienza"
                            " Probabile, fino alla Sofferenza, includendo anche l'eventuale cessione del credito"
                            " o di portafogli e la gestione post-cessione. Rientrano quindi in questo ambito la"
                            " corretta classificazione e transizione tra stati di rischio non performing,"
                            " l'applicazione delle relative regole di stato e dei periodi/rientri previsti, le"
                            " rettifiche di valore e i cambi di metodologia valutativa, il rispetto delle facoltà"
                            " deliberative e gestionali sulle posizioni deteriorate, il processo di concessione"
                            " riferito a controparti già non performing, il monitoraggio specialistico, le azioni"
                            " di recupero, la gestione di posizioni forborne o condivise, nonché la gestione"
                            " contabile e amministrativa tipica delle sofferenze. Il MO copre inoltre i processi"
                            " di cessione di singoli crediti o portafogli, la gestione dei crediti ceduti e le"
                            " operazioni di Credit Risk Transfer.\n\n"
                            "Per il tagging documentale, questo MO intercetta contenuti che trattano il"
                            " trattamento specialistico del credito già deteriorato e delle sue evoluzioni,"
                            " inclusi recupero, valutazione, contabilizzazione e dismissione. Non copre invece il"
                            " credito performing e il suo monitoraggio ordinario, il rating, la concessione del"
                            " credito in bonis, il presidio generale del rischio di credito o la gestione autonoma"
                            " di garanzie e covenant, salvo quando tali temi siano affrontati specificamente nel"
                            " contesto di posizioni non performing."
                        ),
                        odcs=(
                            OdC(
                                code="4612",
                                name="Past due",
                                description=(
                                    "Riguarda la gestione delle esposizioni creditizie scadute nella fase Past Due"
                                    " e la correttezza della loro classificazione e trattamento in tale stato.\n"
                                    "- Classificazione e regole di stato: adeguatezza della classificazione Past"
                                    " Due; funzionamento del motore di calcolo di Gruppo per la classificazione a"
                                    " Past Due; rispetto dei termini di probation period; verifica dei"
                                    " trascinamenti tra i vari stati della fase Past Due; correttezza e coerenza"
                                    " del processo di esclusione dei past due tecnici (sterilizzazione).\n"
                                    "- Facoltà e processo creditizio: rispetto delle Facoltà deliberative e"
                                    " gestionali; correttezza del processo di concessione (istruttoria, delibera e"
                                    " perfezionamento) su controparti in Past due.\n"
                                    "- Gestione della posizione: tempestività delle azioni di recupero; verifiche"
                                    " su Leveraged Transactions; processo di monitoraggio del costo del credito"
                                    " riferito a posizioni Past Due.\n"
                                    "Esclude: le posizioni classificate «Unlikely to Pay», incluse Inadempienza"
                                    " Probabile vetuste o precoci, rettifiche, clienti condivisi, cure period,"
                                    " Inadempienza Probabile Forborne, Add-on e cambio da valutazione statistica"
                                    " ad analitica; le «Sofferenze», incluse proposta/conferma del passaggio a"
                                    " sofferenza, valutazione analitica specifica, gestione contabile, cessione"
                                    " delle sofferenze, legali/fornitori e stralci; i processi di «Cessione e"
                                    " gestione portafogli / crediti» in quanto operazioni di cessione o di"
                                    " gestione di crediti/portafogli ceduti."
                                ),
                            ),
                            OdC(
                                code="5053",
                                name="Unlikely to Pay",
                                description=(
                                    "Riguarda la gestione delle posizioni classificate a Unlikely to Pay /"
                                    " Inadempienza Probabile, inclusi i profili valutativi, di recupero e di"
                                    " monitoraggio propri di tale stato.\n"
                                    "- Classificazione e valutazione: adeguatezza della classificazione, con focus"
                                    " sulle posizioni classificate a Inadempienza Probabile vetuste e sulle"
                                    " classificazioni precoci; adeguatezza delle rettifiche; processo per il"
                                    " cambio della valutazione da statistica ad analitica.\n"
                                    "- Facoltà e presidio gestionale: corretto esercizio delle Facoltà; rispetto"
                                    " delle facoltà deliberative e gestionali; revisione periodica delle posizioni;"
                                    " attività gestionali relative all'Add-on.\n"
                                    "- Gestione della relazione e recupero: gestione dei clienti condivisi, con"
                                    " particolare attenzione ai disallineamenti dello stato amministrativo;"
                                    " tempestività e adeguatezza degli interventi di recupero; processo di"
                                    " concessione (istruttoria, delibera e perfezionamento) su posizioni a"
                                    " Inadempienza Probabile.\n"
                                    "- Forborne e altri focus: monitoraggio delle esposizioni nel cure period;"
                                    " rispetto dei requisiti per la classificazione a Inadempienza Probabile"
                                    " Forborne e per l'uscita dallo stato; verifiche su Leveraged Transactions;"
                                    " processo di monitoraggio del costo del credito riferito a posizioni UTP.\n"
                                    "Esclude: le esposizioni in «Past due», incluse probation period,"
                                    " trascinamenti della fase Past Due, motore di calcolo di Gruppo e past due"
                                    " tecnici/sterilizzazione; le «Sofferenze», incluse passaggio a sofferenza,"
                                    " prima valutazione, revisione annuale o per trigger event, gestione e"
                                    " monitoraggio specialistico del recupero, gestione contabile, cessione,"
                                    " incassi, GBV, spese e stralci; i processi di «Cessione e gestione"
                                    " portafogli / crediti» come operazione di cessione/gestione di portafogli o"
                                    " crediti ceduti e di Credit Risk Transfer."
                                ),
                            ),
                            OdC(
                                code="5054",
                                name="Sofferenze",
                                description=(
                                    "Riguarda la gestione delle posizioni classificate a sofferenza, dalla"
                                    " proposta e conferma del passaggio allo stato, alla valutazione analitica, al"
                                    " recupero, alla contabilizzazione e all'eventuale cessione della posizione.\n"
                                    "- Recupero, cessione e fornitori: gestione e monitoraggio delle attività di"
                                    " recupero; cessione delle sofferenze; gestione e monitoraggio dei fornitori;"
                                    " verifiche sulle attività svolte dai legali esterni tramite Portale Legali.\n"
                                    "- Valutazione, classificazione e Facoltà: adeguatezza delle rettifiche di"
                                    " valore e corretto esercizio delle Facoltà per le posizioni in valutazione"
                                    " analitica specifica effettuata da strutture interne o esterne, incluse"
                                    " attività di valutazione, individuazione della stima di recupero ai fini del"
                                    " calcolo delle rettifiche di valore, tempi di recupero e inserimento della"
                                    " previsione di rientro; adeguatezza della classificazione Sofferenza"
                                    " Forborne; proposta e conferma del passaggio a sofferenza per posizioni in"
                                    " gestione interna o esterna e per posizioni cedute pro-soluto; prima"
                                    " valutazione, revisione annuale e revisione in caso di trigger event.\n"
                                    "- Processo creditizio e Add-on: processo di concessione (istruttoria,"
                                    " delibera e perfezionamento) su posizioni a Sofferenza; attività gestionali"
                                    " relative all'Add-on.\n"
                                    "- Gestione contabile della posizione: voltura contabile; sistemazioni"
                                    " contabili e pareggio delle partite varie e dei sospesi contabili;"
                                    " attribuzione degli incassi su posizioni aperte, chiuse e cedute; incrementi"
                                    " del Gross Book Value (GBV) per ulteriori addebiti e/o escussioni crediti di"
                                    " firma; contabilizzazione delle spese legali e delle spese di recupero;"
                                    " estinzione dei rapporti; gestione e contabilizzazione degli stralci con e"
                                    " senza rinuncia al credito; processo di monitoraggio del costo del credito"
                                    " riferito a posizioni a sofferenza.\n"
                                    "Esclude: la gestione di «Past due», limitata allo scaduto e alle regole della"
                                    " fase Past Due; la gestione «Unlikely to Pay», inclusi classificazioni vetuste"
                                    " o precoci, clienti condivisi, cure period, Inadempienza Probabile Forborne e"
                                    " cambio da valutazione statistica ad analitica; «Cessione e gestione"
                                    " portafogli / crediti» quando l'oggetto è il processo di cessione/gestione di"
                                    " portafogli o singoli crediti ceduti e le operazioni di Credit Risk Transfer"
                                    " in sé, non la gestione della posizione già classificata a sofferenza."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            "AML": RMHierarchy(
                risk_model="AML",
                mos=(
                    MO(
                        code="8838",
                        name="MO Gestione AML",
                        description=(
                            "Il MO Gestione AML copre il presidio complessivo, aziendale e di Gruppo, per la"
                            " prevenzione e il contrasto del riciclaggio, del finanziamento del terrorismo e, ove"
                            " previsto, della proliferazione, considerando insieme assetto di governo, processi"
                            " operativi, controlli e sistemi informativi a supporto degli obblighi normativi."
                            " Rientrano nel suo ambito la definizione e l'aggiornamento di policy, ruoli,"
                            " responsabilità e presidi; l'adeguata verifica della clientela e la profilatura risk"
                            " based lungo il ciclo di vita del rapporto; il monitoraggio dell'operatività per"
                            " individuare anomalie; la valutazione, decisione e trasmissione delle SOS; la"
                            " conservazione, registrazione, messa a disposizione e reporting esterno dei dati AML;"
                            " il rispetto dei divieti e delle restrizioni in materia di antiterrorismo, embarghi,"
                            " contante, strumenti al portatore, moneta elettronica e libretti; il ruolo di"
                            " indirizzo, coordinamento, formazione e controllo di II livello della Funzione"
                            " Antiriciclaggio; l'adeguatezza del MIS a supporto del presidio AML. Il perimetro"
                            " include anche qualità e tracciabilità dei dati e della documentazione,"
                            " esternalizzazioni, flussi verso organi aziendali e Autorità, quality assurance e"
                            " azioni di miglioramento. Non riguarda processi aziendali generali estranei al"
                            " presidio AML, né si limita alla sola dimensione tecnologica, documentale o di"
                            " reporting: il focus è il sistema integrato di prevenzione, rilevazione,"
                            " registrazione, segnalazione e governo del rischio AML/CFT."
                        ),
                        odcs=(
                            OdC(
                                code="5069",
                                name="Adeguata verifica della clientela",
                                description=(
                                    "Riguarda il processo di adeguata verifica della clientela (KYC) in ambito"
                                    " antiriciclaggio e contrasto al finanziamento del terrorismo, in fase di"
                                    " onboarding e di monitoraggio nel continuo della relazione, per rapporti"
                                    " continuativi e operazioni occasionali, con approccio risk based.\n"
                                    "- Policy e modello KYC: policy aggiornate che formalizzano il processo;"
                                    " fattori di rischio relativi a controparti, prodotti, canali distributivi e"
                                    " componente geografica; valutazione del rischio AML; limitazioni operative;"
                                    " strumenti di profilatura; metodologia di calcolo del profilo di rischio"
                                    " riciclaggio con ripercorribilità del modello, manutenzione delle regole e"
                                    " change management.\n"
                                    "- Processo e adempimenti: adeguata verifica ordinaria, semplificata e"
                                    " rafforzata; processi, soluzioni organizzative/procedurali, ruoli e"
                                    " responsabilità; identificazione delle controparti; individuazione di Titolari"
                                    " effettivi (TIE) ed esecutori; rivalutazione e autorizzazione dei profili AML;"
                                    " acquisizione e valutazione di informazioni su scopo e natura dei rapporti e"
                                    " delle operazioni occasionali e sull'origine dei fondi; operatività a"
                                    " distanza; rapporti e operazioni occasionali con paesi terzi ad alto rischio;"
                                    " rapporti di corrispondenza transfrontalieri con intermediari finanziari di"
                                    " paesi terzi; gestione delle attività esternalizzate e relativi modelli"
                                    " operativi/previsioni contrattuali.\n"
                                    "- Presidi e controlli: controlli e autorizzazioni per clientela, TIE e"
                                    " soggetti facoltizzati che richiedono rafforzata verifica; intercettamento e"
                                    " verifica sistematica dei match positivi alle sanction list e alle liste pep"
                                    " ai fini KYC; rispetto di limitazioni e processi autorizzativi per"
                                    " instaurazione di rapporti ed esecuzione di operazioni, incluse quelle"
                                    " occasionali; rispetto delle condizioni limitative poste in fase di"
                                    " autorizzazione della clientela a maggior rischio; quality assurance"
                                    " sistematica sui processi di controllo.\n"
                                    "- Documentazione probatoria: individuazione e conservazione della"
                                    " documentazione a comprova dell'assolvimento degli obblighi KYC, inclusi"
                                    " documenti identificativi, questionario di profilatura antiriciclaggio, set"
                                    " informativo cliente con storicizzazione, valutazioni effettuate nel corso"
                                    " della relazione, documentazione su clientela a maggior rischio AML e scambi"
                                    " informativi con Customer Center/Funzione Antiriciclaggio.\n"
                                    "Esclude: il monitoraggio della movimentazione tramite scenari, alert e routine"
                                    " automatiche («Monitoraggio della movimentazione - Transaction Monitoring»);"
                                    " l'istruttoria e la trasmissione delle SOS e le interlocuzioni con UIF/FIU"
                                    " («Obblighi di segnalazione e comunicazione»); la registrazione nell'archivio"
                                    " ex AUI e il reporting SARA/comunicazioni oggettive («Conservazione e messa a"
                                    " disposizione dei documenti, dei dati e delle informazioni per il contrasto"
                                    " del riciclaggio e del finanziamento del terrorismo»); lo"
                                    " screening/filtering su liste e embarghi e i controlli dual use («Gestione"
                                    " Antiterrorismo e embarghi»); le limitazioni specifiche su contante, assegni,"
                                    " libretti e moneta elettronica («Limitazioni in materia di contante, titoli"
                                    " al portatore, intestazione prodotti di conto, moneta elettronica e"
                                    " libretti»)."
                                ),
                            ),
                            OdC(
                                code="5070",
                                name="Conservazione e messa a disposizione dei documenti, dei dati e delle informazioni per il contrasto del riciclaggio e del finanziamento del terrorismo",
                                description=(
                                    "Riguarda gli obblighi di conservazione, registrazione, messa a disposizione e"
                                    " reporting esterno dei documenti, dei dati e delle informazioni AML/CFT,"
                                    " inclusa la gestione dell'archivio utilizzato dalla Banca e dal Gruppo in"
                                    " continuità con l'Archivio Unico Informatico (AUI).\n"
                                    "- Perimetro informativo da registrare: completezza e aggiornamento delle"
                                    " fattispecie operative da registrare e del set informativo richiesto dalla"
                                    " normativa esterna.\n"
                                    "- Qualità e disponibilità dei dati: accessibilità, tempestività di"
                                    " acquisizione, integrità, trasparenza e storicità delle informazioni"
                                    " registrate.\n"
                                    "- Modalità di conservazione e registrazione: soluzioni complessivamente"
                                    " adottate dall'intermediario per conservazione, messa a disposizione e"
                                    " correlato reporting; corretta registrazione di operazioni, rapporti e"
                                    " soggetti coinvolti nell'archivio ex AUI; corretta gestione dei processi di"
                                    " registrazione da parte delle strutture/soggetti individuati dalla normativa"
                                    " secondo le Regole in materia di conservazione, messa a disposizione e"
                                    " reporting esterno.\n"
                                    "- Assetto operativo: eventuale ricorso ad autonomi centri servizi da parte di"
                                    " Società del Gruppo; soluzioni adottate in caso di esternalizzazione dei"
                                    " servizi di conservazione dei documenti, dei dati e delle informazioni.\n"
                                    "- Reporting esterno: corretta trasmissione dei dati aggregati alla UIF,"
                                    " incluse segnalazioni SARA e comunicazioni oggettive.\n"
                                    "- Controlli: efficacia ed efficienza del sistema dei controlli sulle procedure"
                                    " e sui processi a supporto degli obblighi di conservazione, messa a"
                                    " disposizione e reporting esterno, in tutti i contesti operativi del Gruppo"
                                    " comprese le esternalizzazioni.\n"
                                    "Esclude: la raccolta e la gestione della documentazione a comprova"
                                    " dell'adeguata verifica del singolo cliente e della profilatura KYC"
                                    " («Adeguata verifica della clientela»); le segnalazioni di operazioni"
                                    " sospette/SOS e le relative comunicazioni con UIF/FIU («Obblighi di"
                                    " segnalazione e comunicazione»); la progettazione e qualità del Management"
                                    " Information System a supporto del management («Gestione del Management"
                                    " Information System»); il monitoraggio dell'operatività del cliente per"
                                    " individuare anomalie («Monitoraggio della movimentazione - Transaction"
                                    " Monitoring»)."
                                ),
                            ),
                            OdC(
                                code="4712",
                                name="Obblighi di segnalazione e comunicazione",
                                description=(
                                    "Riguarda il processo di istruttoria, decisione, segnalazione e comunicazione"
                                    " relativo alle Segnalazioni di Operatività Sospetta (SOS) in materia di"
                                    " riciclaggio, finanziamento del terrorismo o finanziamento di programmi di"
                                    " proliferazione di armi di distruzione di massa, nonché i correlati rapporti"
                                    " con Autorità e FIU.\n"
                                    "- Istruttoria e segnalazione SOS: tempestività, completezza, accuratezza e"
                                    " riservatezza del processo per segnalazioni di I livello e di II livello"
                                    " trasmesse all'Autorità.\n"
                                    "- Coordinamento interno: grado di interlocuzione e collaborazione tra i"
                                    " Responsabili della Relazione in caso di clientela condivisa con elementi di"
                                    " sospetto; efficacia dell'attività consulenziale erogata alle strutture"
                                    " operative dalle strutture di Head Office che riportano al Delegato"
                                    " Segnalazioni di Operatività Sospetta (SOS) di Gruppo.\n"
                                    "- Comunicazioni conseguenti alla valutazione: effettiva comunicazione, nel"
                                    " rispetto della riservatezza, degli esiti del processo di valutazione al"
                                    " responsabile di I livello che ha dato origine alla segnalazione; effettiva"
                                    " comunicazione, sempre nel rispetto della riservatezza, dei clienti oggetto"
                                    " di segnalazione alle strutture competenti per l'attribuzione o"
                                    " l'aggiornamento del profilo di rischio.\n"
                                    "- Condivisione infragruppo e rapporti con FIU: scambio informativo tra Head"
                                    " Office Delegato SOS di Gruppo e AML Officer delle Entità del Gruppo, nel"
                                    " rispetto dei limiti del paese ospitante; grado di interlocuzione e"
                                    " collaborazione con le Financial Intelligence Unit e gestione degli esiti"
                                    " della disamina delle SOS ricevute dalle FIU destinatarie.\n"
                                    "- Accessi dell'Autorità: gestione degli adempimenti connessi agli accessi"
                                    " dell'UIF e della Guardia di Finanza.\n"
                                    "Esclude: l'individuazione preventiva di movimentazioni anomale tramite"
                                    " scenari, alert e monitoraggio della movimentazione («Monitoraggio della"
                                    " movimentazione - Transaction Monitoring»); il reporting esterno diverso dalle"
                                    " SOS, come dati aggregati, SARA e comunicazioni oggettive («Conservazione e"
                                    " messa a disposizione dei documenti, dei dati e delle informazioni per il"
                                    " contrasto del riciclaggio e del finanziamento del terrorismo»); la"
                                    " segnalazione al MEF di infrazioni sulle limitazioni di contante e strumenti"
                                    " al portatore («Limitazioni in materia di contante, titoli al portatore,"
                                    " intestazione prodotti di conto, moneta elettronica e libretti»); la sola"
                                    " profilatura/autorizzazione KYC del cliente («Adeguata verifica della"
                                    " clientela»)."
                                ),
                            ),
                            OdC(
                                code="5071",
                                name="Monitoraggio della movimentazione - Transaction Monitoring",
                                description=(
                                    "Riguarda il macro processo di monitoraggio della movimentazione (Transaction"
                                    " Monitoring) volto alla valutazione sistematica e tempestiva dell'operatività"
                                    " della clientela per individuare movimentazioni potenzialmente anomale, con"
                                    " strumenti automatici e manuali e relativi controlli ex post.\n"
                                    "- Impianto di processo: policy aggiornate che descrivono approccio ai fattori"
                                    " di rischio, processi, soluzioni organizzative e strumenti a supporto del"
                                    " monitoraggio.\n"
                                    "- Presidio operativo: valutazione sistematica dell'operatività della clientela"
                                    " da parte del titolare della relazione e delle strutture di competence center;"
                                    " efficacia dell'interazione tra competence center del monitoraggio della"
                                    " movimentazione e competence center del monitoraggio sull'adeguata verifica;"
                                    " condivisione infragruppo delle informazioni sui clienti condivisi, nel"
                                    " rispetto delle limitazioni dei Regulator locali.\n"
                                    "- Monitoraggio automatizzato: caratteristiche, efficacia ed efficienza degli"
                                    " strumenti automatici; ripercorribilità e sostenibilità delle scelte di"
                                    " monitoraggio tramite algoritmi/scenari; coverage analysis rispetto agli"
                                    " indicatori di anomalia delle Autorità di Vigilanza e delle Istituzioni"
                                    " sovranazionali; revisione e validazione periodica di good guy list/exemption"
                                    " list e liste paese; manutenzione, validazione e periodica revisione del set"
                                    " di scenari e delle regole in funzione di contesto normativo/operativo e dei"
                                    " ritorni sugli alert; qualità, adeguatezza e completezza delle basi dati"
                                    " alimentanti; strumenti tecnologici per analisi preliminari e interventi"
                                    " manutentivi sulle routine.\n"
                                    "- Monitoraggio manuale: soluzioni adottate nei contesti in cui gli strumenti"
                                    " automatici hanno valenza limitata o sono assenti.\n"
                                    "- Controlli e miglioramento: sistema dei controlli ex post sulle attività di"
                                    " monitoraggio della movimentazione e attività di quality assurance orientate"
                                    " all'individuazione sistematica delle azioni di miglioramento.\n"
                                    "Esclude: l'identificazione del cliente, i TIE/esecutori, la profilatura AML e"
                                    " le autorizzazioni KYC («Adeguata verifica della clientela»); l'istruttoria e"
                                    " la trasmissione delle SOS all'Autorità («Obblighi di segnalazione e"
                                    " comunicazione»); lo screening/filtering su liste antiterrorismo/embarghi,"
                                    " incluse liste UE/ONU/OFAC e controlli dual use («Gestione Antiterrorismo e"
                                    " embarghi»); la gestione del MIS come architettura dei flussi informativi di"
                                    " management («Gestione del Management Information System»)."
                                ),
                            ),
                            OdC(
                                code="5072",
                                name="Limitazioni in materia di contante, titoli al portatore, intestazione prodotti di conto, moneta elettronica e libretti",
                                description=(
                                    "Riguarda il rispetto delle limitazioni normative e dei correlati obblighi di"
                                    " segnalazione in materia di contante, titoli al portatore, intestazione"
                                    " prodotti di conto, moneta elettronica e libretti, tenendo conto dello"
                                    " specifico ambito organizzativo e di business e, ove applicabile, degli"
                                    " ordinamenti del paese di insediamento della filiale estera e/o della banca"
                                    " del Gruppo.\n"
                                    "- Operazioni in contante: corretta esecuzione, gestione e disamina di merito"
                                    " dei presupposti e dell'origine dei fondi delle operazioni oltre soglia e/o"
                                    " perfezionate con utilizzo di tagli elevati; effettivo presidio e piena"
                                    " tracciatura/ripercorribilità delle transazioni di passaggio contanti tra"
                                    " soggetti diversi.\n"
                                    "- Assegni e strumenti al portatore: corretta acquisizione della"
                                    " documentazione a supporto delle richieste di carnet assegni senza clausola"
                                    " di intrasferibilità e di assegni circolari liberi; corretta esecuzione delle"
                                    " residuali attività di rimborso certificati di deposito al portatore e cambio"
                                    " titolarità di libretti al portatore.\n"
                                    "- Divieti su anonimato/fittizietà: adeguatezza dei processi aziendali a"
                                    " garantire il rispetto del divieto di apertura e utilizzo di conti e libretti"
                                    " di risparmio in forma anonima o fittizia e del divieto di utilizzo di"
                                    " prodotti di moneta elettronica anonimi.\n"
                                    "- Segnalazioni e controlli: rispetto degli obblighi di segnalazione al MEF"
                                    " delle infrazioni; adeguatezza del sistema dei controlli e degli strumenti a"
                                    " supporto, anche con riferimento alle esternalizzazioni.\n"
                                    "Esclude: la generale adeguata verifica del cliente e la profilatura AML,"
                                    " inclusa la raccolta di informazioni su scopo/natura del rapporto («Adeguata"
                                    " verifica della clientela»); il monitoraggio della movimentazione per"
                                    " individuare anomalie e generare alert («Monitoraggio della movimentazione -"
                                    " Transaction Monitoring»); le SOS verso l'Autorità («Obblighi di segnalazione"
                                    " e comunicazione»); la registrazione ex AUI e il reporting SARA/comunicazioni"
                                    " oggettive («Conservazione e messa a disposizione dei documenti, dei dati e"
                                    " delle informazioni per il contrasto del riciclaggio e del finanziamento del"
                                    " terrorismo»)."
                                ),
                            ),
                            OdC(
                                code="4714",
                                name="Gestione Antiterrorismo e embarghi",
                                description=(
                                    "Riguarda il presidio dei divieti e degli obblighi limitativi"
                                    " sull'instaurazione di relazioni e sull'operatività in ambito Antiterrorismo"
                                    " ed Embarghi, tramite processi di screening, filtering e transaction check e"
                                    " relativi controlli.\n"
                                    "- Divieti e restrizioni: rispetto dei divieti e degli obblighi limitativi"
                                    " dell'instaurazione di relazioni e dell'operatività in ambito Antiterrorismo"
                                    " ed Embarghi.\n"
                                    "- Liste e algoritmi di detection: adeguatezza dei processi di screening,"
                                    " filtering e transaction check; manutenzione delle liste esterne (UE, ONU,"
                                    " USA/OFAC e liste locali dei singoli Stati in cui opera il Gruppo) e delle"
                                    " liste interne; grado di integrazione delle liste nelle procedure automatiche"
                                    " di detection; adeguatezza degli algoritmi di detection; processi di"
                                    " esclusione da successivi alert per i soggetti per cui il match con liste"
                                    " esterne è stato escluso come anomalo (good guy list).\n"
                                    "- Controlli operativi: presenza di processi di controllo, declinati e agiti,"
                                    " sulle verifiche della natura dual use delle merci oggetto di esportazione;"
                                    " definizione dei livelli di responsabilità e delle attività di controllo;"
                                    " effettuazione delle verifiche previste; tracciabilità e conservazione della"
                                    " documentazione dei controlli effettuati.\n"
                                    "- Strumenti di Artificial Intelligence: processi declinati e agiti relativi"
                                    " al monitoraggio del funzionamento (performance e controlli), all'effettiva"
                                    " manutenzione e alle logiche di implementazione degli strumenti di Artificial"
                                    " Intelligence utilizzati per le attività di transaction filtering, ad oggi"
                                    " tool Pelican.\n"
                                    "Esclude: la profilatura AML del cliente, i TIE/esecutori e i match alle liste"
                                    " gestiti ai fini di adeguata verifica/autorizzazione KYC («Adeguata verifica"
                                    " della clientela»); il monitoraggio della movimentazione tramite scenari di"
                                    " anomalia su operatività e relative good guy list/exemption list del"
                                    " transaction monitoring («Monitoraggio della movimentazione - Transaction"
                                    " Monitoring»); l'istruttoria e l'invio delle SOS («Obblighi di segnalazione e"
                                    " comunicazione»); le limitazioni su contante, assegni, libretti e moneta"
                                    " elettronica («Limitazioni in materia di contante, titoli al portatore,"
                                    " intestazione prodotti di conto, moneta elettronica e libretti»)."
                                ),
                            ),
                            OdC(
                                code="5073",
                                name="Ruolo e Processi di Governo assegnati alla Funzione Antiriciclaggio",
                                description=(
                                    "Riguarda l'assetto, il ruolo di II livello, i compiti di governo e il"
                                    " coordinamento di Gruppo assegnati alla Funzione Antiriciclaggio, attualmente"
                                    " collocata nell'area del Chief Compliance Office, non l'esecuzione operativa"
                                    " dei singoli processi AML.\n"
                                    "- Assetto della Funzione: adeguatezza della Funzione Antiriciclaggio rispetto"
                                    " alla normativa domestica, primaria e secondaria, nonché alle best practices"
                                    " declinate nella normativa e negli orientamenti europei e degli Stati esteri"
                                    " in cui è presente il Gruppo.\n"
                                    "- Governo normativo e procedurale: identificazione delle norme applicabili e"
                                    " valutazione del loro impatto su processi e procedure interne, con conseguente"
                                    " rilascio e aggiornamento dei processi operativi; aggiornamento sistematico"
                                    ' delle "Linee Guida per il contrasto ai fenomeni di riciclaggio, di'
                                    ' finanziamento del terrorismo e per la gestione degli embarghi".\n'
                                    "- Presidio di II livello sui rischi: valutazione nel continuo"
                                    " dell'adeguatezza del processo di gestione dei rischi antiriciclaggio, delle"
                                    " procedure a supporto dei macro-processi anti financial crime e del sistema"
                                    " dei controlli interni, inclusi strumenti, flussi informativi alimentanti,"
                                    " quality assurance e tempestiva attivazione delle azioni correttive; esercizio"
                                    " annuale del risk assessment e utilizzo delle risultanze per efficientamento"
                                    " dei controlli e gestione delle priorità di intervento; valutazione"
                                    " preventiva del rischio di riciclaggio correlato a nuovi prodotti e servizi e"
                                    " disamina degli esiti delle attività di controllo.\n"
                                    "- Supporto, reporting e formazione: supporto specialistico e predisposizione"
                                    " di flussi informativi specifici agli organi aziendali e all'alta direzione,"
                                    " inclusa l'informativa tempestiva su violazioni e carenze; disegno e"
                                    " contribuzione sistematica; predisposizione di un adeguato piano formativo e"
                                    " monitoraggio sulla fruizione; collaborazione e corretta gestione dei processi"
                                    " di segnalazione periodica verso l'Autorità; presidio su esternalizzazioni e"
                                    " contratti di outsourcing infragruppo.\n"
                                    "- Coordinamento di Gruppo: in raccordo con l'OdC del RM Governance riferito"
                                    " alla governance delle Subsidiaries, efficacia dell'azione di governo del"
                                    " rischio AML e del ruolo di coordinamento della Funzione Antiriciclaggio di"
                                    " Gruppo nella definizione, messa a disposizione e verifica di efficacia di"
                                    " procedure/processi per coordinamento e condivisione delle informazioni"
                                    " rilevanti e valutazione dei rischi AML; standard generali su adeguata"
                                    " verifica, conservazione dei dati, monitoraggio dell'operatività e"
                                    " individuazione/segnalazione di operazioni sospette; azione di indirizzo e"
                                    " coordinamento sui percorsi formativi dedicati, salvaguardando i limiti degli"
                                    " ordinamenti locali.\n"
                                    "Esclude: l'esecuzione operativa dei singoli macro-processi «Adeguata verifica"
                                    " della clientela», «Conservazione e messa a disposizione dei documenti, dei"
                                    " dati e delle informazioni per il contrasto del riciclaggio e del"
                                    " finanziamento del terrorismo», «Obblighi di segnalazione e comunicazione»,"
                                    " «Monitoraggio della movimentazione - Transaction Monitoring» e «Gestione"
                                    " Antiterrorismo e embarghi»; la gestione tecnica/architetturale del MIS come"
                                    " sistema informativo di management («Gestione del Management Information"
                                    " System»)."
                                ),
                            ),
                            OdC(
                                code="5074",
                                name="Gestione del Management Information System",
                                description=(
                                    "Riguarda l'adeguatezza, la completezza, l'alimentazione e il funzionamento"
                                    " del Management Information System (MIS) a supporto dei processi e delle"
                                    " informazioni chiave antiriciclaggio, quale sistema dei flussi informativi"
                                    " aziendali per il presidio dei rischi di conformità AML.\n"
                                    "- Adeguatezza del sistema informativo: conformità del MIS a quanto richiesto"
                                    " dalla normativa di riferimento per processi AML e informazioni chiave"
                                    " antiriciclaggio.\n"
                                    "- Contribuzione al presidio dei rischi: effettivo contributo del MIS, tempo"
                                    " per tempo in essere, alla corretta attuazione del presidio di gestione dei"
                                    " rischi.\n"
                                    "- Componenti del MIS: grado di sviluppo e di alimentazione dei sistemi di"
                                    " raccolta dati dalle fonti alimentanti (Transaction Processing System), dei"
                                    " sistemi gestionali per finalità di analisi delle informazioni (Management"
                                    " Support System) e dei modelli informatici a supporto del processo"
                                    " decisionale, inclusi eventuali componenti di artificial intelligence"
                                    " (Decision Support System - Expert System).\n"
                                    "- Qualità delle informazioni: tempestività, attendibilità, accuratezza e"
                                    " significatività delle informazioni elaborate, comparate con la ragionevolezza"
                                    " dei correlati costi di gestione e di sviluppo a tendere del complessivo"
                                    " impianto informativo.\n"
                                    "- Funzionamento e fruizione: modalità di gestione ed effettivo funzionamento"
                                    " del MIS rispetto alla raccolta, archiviazione, elaborazione e distribuzione"
                                    " dei dati tramite viste idonee per i singoli ruoli del management e per gli"
                                    " organi societari, a supporto della valutazione dei presidi in essere e delle"
                                    " decisioni sugli interventi da attivare e sulle relative tempistiche.\n"
                                    "Esclude: gli archivi regolamentari ex AUI e il reporting esterno verso UIF,"
                                    " incluse SARA e comunicazioni oggettive («Conservazione e messa a disposizione"
                                    " dei documenti, dei dati e delle informazioni per il contrasto del riciclaggio"
                                    " e del finanziamento del terrorismo»); il ruolo di governo della Funzione"
                                    " Antiriciclaggio e la produzione di flussi informativi come responsabilità di"
                                    " II livello («Ruolo e Processi di Governo assegnati alla Funzione"
                                    " Antiriciclaggio»); il contenuto operativo dei processi KYC, Transaction"
                                    " Monitoring, SOS, Antiterrorismo/embarghi e limitazioni sul contante, che il"
                                    " MIS supporta ma non sostituisce."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        }
    )
