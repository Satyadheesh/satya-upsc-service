## UPSC eval — prompt v2.3, Qwen2.5-14B-Instruct-Q4_K_M (score ≥ 3) — ❌ FAIL

| metric | result | target |
|---|---|---|
| false positives on `no` | 18/87 (21%) | ≤ 10% |
| recall on `yes` | 10/11 (91%) | ≥ 80% |
| subject accuracy | 9/10 (90%) | ≥ 80% |
| borderline passed | 14/22 (64%) | – |
| errors | 0 | 0 |

v1 baseline: false positives 64%, recall 82%. v2.0: FP 1%, recall 27%. v2.1: FP 34%, recall 100%. v2.2 (7B): FP 26%, recall 100%.

### By threshold
| keep score ≥ | FP on `no` | recall on `yes` | borderline kept |
|---|---|---|---|
| 2 | 23/87 (26%) | 10/11 (91%) | 16/22 (73%) |
| 3 (current) | 18/87 (21%) | 10/11 (91%) | 14/22 (64%) |
| 4 | 3/87 (3%) | 6/11 (55%) | 4/22 (18%) |

### False positives
- s=5 Brazil: Bolsonaro ordered to start serving 27-year prison sentence for coup plot — _global_affairs/international_other: Major political development in Brazil_
- s=3 Margi Sathi Smriti Puraskaram for Kalamandalam Gopi and Chitra Visweswaran - The Hindu — _history_culture/national: Cultural awards for performing arts_
- s=4 Four dead in Russian attack as diplomatic efforts to end war continue — _global_affairs/international_other: Russian attack, diplomatic efforts, war updates_
- s=3 APCRDA project office bags IGBC Net Zero Energy rating - The Hindu — _science_tech/national: First govt building gets Net Zero Energy rating_
- s=3 Delhi court extends gangster Anmol Bishnoi's NIA custody till December 5 - The Hindu — _internal_security/national: NIA custody extension for gangster_
- s=3 Emphasis laid on upholding Constitutional values - The Hindu — _constitutional_authority/national: Constitution Day celebration, Preamble reading_
- s=3 Appear before court or face non-bailable warrant: Telangana HC to HYDRAA Commissioner - Th — _court_constitutional/national: Contempt case against HYDRAA Commissioner_
- s=4 Hondurans vote amid Trump threat to cut aid if his preferred candidate loses | Honduras |  — _global_affairs/international_other: US intervention in Honduras election_
- s=3 Kerala government orders rollback of UGC, AICTE incentive increments - The Hindu — _law_policy_scheme/state: State policy on teacher increments_
- s=3 Enforcement Directorate conducting searches under FEMA into ‘suspected hawala operator’ -  — _internal_security/national: Anti-money laundering operation_
- s=3 KFRI signs MoU with Odisha Bamboo Development Agency - The Hindu — _law_policy_scheme/national: MoU for bamboo sector development_
- s=3 86 respondents bound over as Hyderabad Police act against ten rival gangs - The Hindu — _internal_security/national: Gang violence crackdown_
- s=3 Lokesh, Anitha in Delhi for talks on cyclone impact and pending issues - The Hindu — _india_foreign_relations/national: Ministers meet Union govt on Andhra issues_
- s=3 America benefited from talented Indians, but one can’t game H1B system: Elon Musk - The Hi — _india_foreign_relations/international_india: Elon Musk comments on H1B, US-India relations_
- s=3 Amaravati to have ‘Cosmos Planetarium’ under MoU with Indian Institute of Astrophysics - T — _science_tech/national: State-of-the-art planetarium in Amaravati_
- s=3 Govt. medical college doctors in Kozhikode boycott OP duty - The Hindu — _society_data/national: Healthcare worker agitation, patient impact_
- s=3 NTR Bharosa pensions to be delivered at homes in Eluru on December 1 - The Hindu — _law_policy_scheme/national: NTR Bharosa pension scheme update_
- s=3 Manesar violence: terminated Maruti worker’s petition for reinstatement junked - The Hindu — _internal_security/national: Discipline in workforce, legal battle_

### Missed
- s=0 Hyderabad’s NTR Stadium turns sea of faith as thousands observe 350th martyrdom of Guru Te — _none/local: No exam relevance_

### Sample notes
**Droupadi Murmu becomes first President to address Odisha Assembly - The Hindu** — GS2 › polity › constitutional_bodies ✅
- Why: President Droupadi Murmu became the first President to address the Odisha Legislative Assembly, marking a historic moment.
- Q: Discuss the significance of President Droupadi Murmu addressing the Odisha Legislative Assembly and the initiatives she highlighted.

**Jakarta overtakes Tokyo as world’s most populous city, according to UN | Indonesia | The G** — GS1 › society › urbanisation ✅
- Why: Jakarta has overtaken Tokyo as the world’s most populous city according to a UN study, highlighting the rapid urbanisation trends.
- [report_index] World Urbanisation Prospects 2025 report by UN
- [data_fact] Jakarta's population is 42 million
- [data_fact] Tokyo's population is 33 million
- [data_fact] Nine out of the 10 most populated cities are in Asia
- Q: Discuss the implications of Jakarta overtaking Tokyo as the world's most populous city in the context of urbanisation and its socio-economic impacts.

**India-UAE FTA Talks: Market access, gold quota and data sharing reviewed under CEPA - The ** — GS2 › ir › neighbourhood ✅
- Why: India and UAE reviewed market access, gold quota, and data sharing under CEPA to boost economic ties.
- [international_org] CEPA: India-UAE trade pact in force since May 2022
- [data_fact] India-UAE bilateral trade crossed $100 billion in 2024-25
- [data_fact] India-UAE target non-oil and non-precious metal trade to $100 billion by 2030
- Q: Discuss the implications of the Comprehensive Economic Partnership Agreement (CEPA) between India and the UAE on bilateral trade and economic cooperation.

**Proposal for new design of border fencing under consideration of Centre: BSF IG - The Hind** — GS3 › security › border_management ✅
- Why: BSF IG proposes new design of border fencing along India-Bangladesh border to enhance border management.
- [place] India-Bangladesh border: 4,096 km total, 856 km in Tripura
- [institution] BSF: under the Ministry of Home Affairs
- [data_fact] Heavy rainfall in Tripura has affected the existing border fencing
- Q: Discuss the challenges and implications of enhancing border management through the proposed new design of border fencing along the India-Bangladesh border.

**What is going wrong in Tamil Nadu’s SIR? | Focus Tamil Nadu - The Hindu** — GS2 › polity › elections ✅
- Why: Tamil Nadu's Special Intensive Revision (SIR) process for voter list updates has faced significant issues, threatening the deletion of many genuine voters.
- Q: Discuss the challenges faced by Tamil Nadu's Special Intensive Revision (SIR) process for voter list updates and suggest measures to ensure the inclusion of genuine voters.

**Manipur's violence-hit people, seeking to return home, clash with security forces - The Hi** — GS3 › disaster › natural_disasters ❌ want ['security']
- Why: Displaced people in Manipur clashed with security forces while trying to return home after ethnic violence.
- Q: Discuss the challenges faced by internally displaced persons (IDPs) in Manipur and the role of security forces in managing such situations.

**EC tells Supreme Court Centre’s citizenship scrutiny powers are limited - The Hindu** — GS2 › polity › constitutional_bodies ✅
- Why: The Election Commission of India dismissed arguments that only the Union government has exclusive authority to scrutinise citizenship, asserting its own powers under the Constitution.
- [act_bill] Citizenship Act, 1955: Section 9 deals with termination of citizenship for voluntary acquisition of foreign citizenship
- [constitution] Article 324: Empowers the EC to supervise and control the conduct of elections
- [constitution] Article 326: Specifies conditions for voter eligibility, including citizenship
- Q: Discuss the constitutional powers of the Election Commission of India in relation to the scrutiny of citizenship for electoral purposes.

**PM Modi calls Sri Lankan President to offer continued support with cyclone relief - The Hi** — GS2 › ir › neighbourhood ✅
- Why: PM Modi assured Sri Lanka of continued support for cyclone relief under Operation Sagar Bandhu.
- [international_org] Operation Sagar Bandhu: India's humanitarian assistance and disaster relief (HADR) mission for Sri Lanka
- [data_fact] India has provided 53 tonnes of relief material to Sri Lanka
- [place] Sri Lanka sought international help after Cyclone Ditwah
- Q: Evaluate the role of Operation Sagar Bandhu in India's disaster management framework.

**Over 68% SIR enumeration forms digitised: ECI - The Hindu** — GS2 › polity › elections ✅
- Why: Election Commission reports progress on digitising enumeration forms for the Special Intensive Revision (SIR) of electoral rolls in 12 States and UTs.
- [institution] Election Commission of India (ECI) conducting Special Intensive Revision (SIR) of electoral rolls
- [data_fact] Over 68% of enumeration forms digitised till Nov 27, 2025
- [data_fact] Enumeration phase ends on December 4, 2025
- Q: Discuss the significance of the Special Intensive Revision (SIR) of electoral rolls and the challenges faced in its implementation.

**Putin is coming to India in December 2025: Which other Russian presidents visited India, i** — GS2 › ir › neighbourhood ✅
- Why: Putin's upcoming state visit to India in December 2025 is set to reinforce the India-Russia Special and Privileged Strategic Partnership.
- [international_org] India-Russia Annual Summit: 23rd edition scheduled for December 2025
- [person_post] Vladimir Putin: Acting President of Russia since 31 December 1999, formally elected on 7 May 2000
- [data_fact] Putin's presidency marked the beginning of renewed emphasis on closer India-Russia ties
- Q: Discuss the significance of President Putin's upcoming visit to India in the context of India-Russia strategic partnership.

