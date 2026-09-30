## UPSC eval — prompt v2.5, gemma-4-12b-it-Q4_K_M (score ≥ 3) — ❌ FAIL

| metric | result | target |
|---|---|---|
| false positives on `no` | 3/87 (3%) | ≤ 10% |
| recall on `yes` | 8/11 (73%) | ≥ 80% |
| subject accuracy | 7/8 (88%) | ≥ 80% |
| borderline passed | 5/22 (23%) | – |
| errors | 0 | 0 |

v1 baseline: false positives 64%, recall 82%. v2.0: FP 1%, recall 27%. v2.1: FP 34%, recall 100%. v2.2 (7B): FP 26%, recall 100%. v2.3: Qwen14B FP 21%/recall 91%, Gemma4-12B FP 3%/recall 73%, Gemma4-E4B FP 25%/recall 91%.

### By threshold
| keep score ≥ | FP on `no` | recall on `yes` | borderline kept |
|---|---|---|---|
| 2 | 10/87 (11%) | 8/11 (73%) | 8/22 (36%) |
| 3 (current) | 3/87 (3%) | 8/11 (73%) | 5/22 (23%) |
| 4 | 0/87 (0%) | 3/11 (27%) | 1/22 (5%) |

### False positives
- s=3 APCRDA project office bags IGBC Net Zero Energy rating - The Hindu — _environment/state: First government building in India to receive IGBC Net Zero Energy Rating._
- s=3 Kerala government orders rollback of UGC, AICTE incentive increments - The Hindu — _law_policy_scheme/state: State-level policy change regarding teacher pay and administrative jurisdiction._
- s=3 KFRI signs MoU with Odisha Bamboo Development Agency - The Hindu — _law_policy_scheme/national: Inter-state cooperation on bamboo research, technology transfer, and livelihood schemes._

### Missed
- s=0 Hyderabad’s NTR Stadium turns sea of faith as thousands observe 350th martyrdom of Guru Te — _none/local: Religious event/observance without policy or national significance._
- s=0 Manipur's violence-hit people, seeking to return home, clash with security forces - The Hi — _none/state: Individual criminal incidents and local clashes do not fit UPSC hooks._
- s=1 EC tells Supreme Court Centre’s citizenship scrutiny powers are limited - The Hindu — _elections_process/national capped:party-political: EC's authority on citizenship scrutiny and electoral roll revision rules._

### Sample notes
**Droupadi Murmu becomes first President to address Odisha Assembly - The Hindu** — GS1 › history_culture › post_independence ❌ want ['polity']
- Why: President Droupadi Murmu became the first President of India to address the Odisha Legislative Assembly, returning to the house where she began her legislative career in 2000.
- [person_post] Droupadi Murmu is the current President of India.
- [data_fact] President Murmu began her legislative career in the year 2000.
- [data_fact] The President was adjudged the best legislator in the year 2007.
- [scheme] Subhadra scheme: A state-level initiative in Odisha for women's empowerment.
- Q: Discuss the significance of the President's role in fostering federal cooperation and the symbolic importance of representative leadership in Indian democracy.

**Jakarta overtakes Tokyo as world’s most populous city, according to UN | Indonesia | The G** — GS1 › society › urbanisation ✅
- Why: The UN World Urbanisation Prospects 2025 report identifies Jakarta as the world's most populous city due to revised geospatial and population criteria.
- [data_fact] Jakarta population: 42 million (UN World Urbanisation Prospects 2025)
- [data_fact] Tokyo population: 33 million (defined as a megalopolis including Saitama, Chiba, and Kanagawa)
- [data_fact] Number of megacities (10M+ inhabitants) increased from 8 in 1975 to 33 in 2025
- [data_fact] Global urban population growth: 20% in 1950 to nearly 50% currently
- [data_fact] Projected urban growth: Two-thirds of global population growth expected in cities by 2050
- Q: Discuss the socio-economic implications of rapid urbanisation in Asian megacities and the challenges of managing inclusive urban growth by 2050.

**India-UAE FTA Talks: Market access, gold quota and data sharing reviewed under CEPA - The ** — GS2 › ir › bilateral ✅
- Why: India and the UAE held a joint committee meeting to review the Comprehensive Economic Partnership Agreement (CEPA) to enhance trade and regulatory cooperation.
- [international_org] CEPA: A Comprehensive Economic Partnership Agreement between India and the UAE.
- [data_fact] Bilateral trade volume: Crossed $100 billion in the 2024-25 period.
- [data_fact] Target: $100 billion in non-oil and non-precious metal trade by 2030.
- [institution] APEDA: Agricultural and Processed Food Products Export Development Authority, involved in food safety MoUs.
- [data_fact] Gold TRQ: India now allocates gold Tariff Rate Quotas through a transparent competitive bidding process.
- Q: Examine how Comprehensive Economic Partnership Agreements (CEPAs) can serve as catalysts for diversifying India's export basket beyond traditional commodities.

**Proposal for new design of border fencing under consideration of Centre: BSF IG - The Hind** — GS3 › security › border_management ✅
- Why: The BSF IG announced that the Ministry of Home Affairs is considering a proposal for a new design of barbed wire fencing along the India-Bangladesh border to replace aging infrastructure.
- [data_fact] India-Bangladesh international border length is 4,096 km.
- [data_fact] Tripura shares 856 km of its border with Bangladesh.
- [institution] BSF (Border Security Force) operates under the Ministry of Home Affairs (MHA).
- [institution] BGB (Border Guard Bangladesh) is the primary border guarding agency of Bangladesh.
- Q: Discuss the significance of integrated border management and infrastructure modernization in curbing transnational crimes like cattle smuggling along the India-Bangladesh border.

**What is going wrong in Tamil Nadu’s SIR? | Focus Tamil Nadu - The Hindu** — GS2 › polity › elections ✅
- Why: The Special Intensive Revision (SIR) in Tamil Nadu is facing operational failures, potentially leading to the mass deletion of genuine voters before the 2026 elections.
- [institution] Election Commission of India (ECI) is the constitutional body responsible for voter list maintenance and conducting elections.
- [data_fact] The Special Intensive Revision (SIR) is a periodic exercise to ensure the accuracy of the electoral roll.
- [place] Tamil Nadu is the state where the current SIR operational issues were reported in November 2025.
- Q: Critically analyze the challenges in maintaining accurate electoral rolls and suggest measures to ensure inclusive voter participation during intensive revision cycles.

**PM Modi calls Sri Lankan President to offer continued support with cyclone relief - The Hi** — GS2 › ir › neighbourhood ✅
- Why: PM Modi assured Sri Lanka of continued support under 'Operation Sagar Bandhu' to assist in relief and rehabilitation following the devastation caused by Cyclone Ditwah.
- [institution] Operation Sagar Bandhu: India's specific humanitarian assistance and disaster relief (HADR) mission for Sri Lanka.
- [data_fact] India has provided 53 tonnes of relief material to Sri Lanka as of December 1, 2025.
- [place] Cyclone Ditwah: The specific cyclone causing devastation in Sri Lanka in late 2025.
- [data_fact] NDRF teams were dispatched to Sri Lanka for search and rescue operations on November 29, 2025.
- Q: Examine the significance of India's 'Neighborhood First' policy in the context of its Humanitarian Assistance and Disaster Relief (HADR) operations in South Asia.

**Over 68% SIR enumeration forms digitised: ECI - The Hindu** — GS2 › polity › elections ✅
- Why: The Election Commission of India (ECI) reported the progress of digitising enumeration forms during the second phase of the Special Intensive Revision (SIR) of electoral rolls.
- [data_fact] Total electors covered in the second phase of SIR: 50,97,44,423
- [data_fact] Digitisation progress as of November 27, 2025: 68.03% of total forms
- [place] States/UTs in SIR phase: Chhattisgarh, Goa, Gujarat, Kerala, Madhya Pradesh, Rajasthan, Tamil Nadu, Uttar Pradesh, West Bengal, Puducherry, Andaman and Nicobar Islands, Lakshadweep
- [institution] Booth Level Officers (BLOs) are responsible for collecting forms and uploading data to the ECI website via dedicated apps
- [data_fact] Lakshadweep achieved the highest digitisation rate at 99.9% as of November 2025
- Q: Discuss how the digitisation of electoral rolls through Special Intensive Revisions contributes to the integrity of the democratic process in India.

**Putin is coming to India in December 2025: Which other Russian presidents visited India, i** — GS2 › ir › bilateral ✅
- Why: President Vladimir Putin is scheduled to visit India in December 2025 for the 23rd India-Russia Annual Summit to review strategic, defense, and energy cooperation.
- [data_fact] The 23rd India-Russia Annual Summit is scheduled for December 2025.
- [person_post] Vladimir Putin became Acting President of Russia on 31 December 1999 and was formally elected on 7 May 2000.
- [data_fact] Key defense projects under review include the S-400 missile system and Su-57 fighter jets.
- [data_fact] The diplomatic framework is defined as a 'Special and Privileged Strategic Partnership'.
- Q: Examine the evolution of the India-Russia 'Special and Privileged Strategic Partnership' in the context of shifting global geopolitical dynamics and defense cooperation.

