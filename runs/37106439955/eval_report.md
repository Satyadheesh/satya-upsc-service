## UPSC eval — prompt v2.6, gemma-4-12b-it-Q4_K_M (score ≥ 3) — ✅ PASS

| metric | result | target |
|---|---|---|
| false positives on `no` | 3/87 (3%) | ≤ 10% |
| recall on `yes` | 10/11 (91%) | ≥ 80% |
| subject accuracy | 10/10 (100%) | ≥ 80% |
| borderline passed | 7/22 (32%) | – |
| errors | 0 | 0 |

v1 baseline: false positives 64%, recall 82%. v2.0: FP 1%, recall 27%. v2.1: FP 34%, recall 100%. v2.2 (7B): FP 26%, recall 100%. v2.3: Qwen14B FP 21%/recall 91%, Gemma4-12B FP 3%/recall 73%, Gemma4-E4B FP 25%/recall 91%.

### By threshold
| keep score ≥ | FP on `no` | recall on `yes` | borderline kept |
|---|---|---|---|
| 2 | 12/87 (14%) | 10/11 (91%) | 9/22 (41%) |
| 3 (current) | 3/87 (3%) | 10/11 (91%) | 7/22 (32%) |
| 4 | 0/87 (0%) | 4/11 (36%) | 0/22 (0%) |

### False positives
- s=3 APCRDA project office bags IGBC Net Zero Energy rating - The Hindu — _environment/state: First government building in India to receive IGBC Net Zero Energy Rating._
- s=3 KFRI signs MoU with Odisha Bamboo Development Agency - The Hindu — _law_policy_scheme/national: Inter-state cooperation on bamboo research, technology transfer, and livelihood schemes._
- s=3 Kerala government orders rollback of UGC, AICTE incentive increments - The Hindu — _law_policy_scheme/state: State government policy on academic pay revisions and administrative jurisdiction._

### Missed
- s=1 Hyderabad’s NTR Stadium turns sea of faith as thousands observe 350th martyrdom of Guru Te — _history_culture/local: Local religious event; minor relevance for history/culture section._

### Sample notes
**Droupadi Murmu becomes first President to address Odisha Assembly - The Hindu** — GS2 › polity › constitution ✅
- Why: President Droupadi Murmu became the first President of India to address the Odisha Legislative Assembly, returning to the house where she began her legislative career in 2000.
- [data_fact] President Murmu began her legislative career in the year 2000
- [data_fact] The President received an additional Rs. 800 per quintal as an input subsidy over and above the MSP for paddy in Odisha
- [scheme] Subhadra scheme: A state initiative in Odisha for women's empowerment
- [data_fact] President Murmu was adjudged the best legislator in 2007
- Q: Discuss the significance of the President's role in fostering federal cooperation and the symbolic importance of the Head of State's interaction with State Legislatures.

**Manipur's violence-hit people, seeking to return home, clash with security forces - The Hi** — GS3 › security › lwe ✅
- Why: Displaced people in Manipur clashed with security forces at Yaingangpokpi while attempting to return to their homes in the Senapati district.
- [place] Imphal East and Senapati are districts in the state of Manipur.
- [data_fact] Ethnic violence in Manipur began in May 2023.
- [data_fact] The Sangai Festival began on November 21, 2025.
- Q: Examine the challenges in managing internal displacement and restoring communal harmony in conflict-affected regions like Manipur.

**India-UAE FTA Talks: Market access, gold quota and data sharing reviewed under CEPA - The ** — GS2 › ir › bilateral ✅
- Why: The Commerce Ministry announced that the joint committee under the India-UAE Comprehensive Economic Partnership Agreement (CEPA) reviewed market access, gold import quotas, and data sharing to boost economic ties.
- [data_fact] Bilateral trade between India and UAE crossed $100 billion in 2024-25.
- [data_fact] Target for non-oil and non-precious metal trade is $100 billion by 2030.
- [institution] APEDA (Agricultural and Processed Food Products Export Development Authority) is involved in food safety MoU with UAE.
- [place] UAE (United Arab Emirates) is a key trading partner under the CEPA framework.
- [sci_tech] The committee discussed data sharing and gold Tariff Rate Quota (TRQ) allocation.
- Q: Examine how the India-UAE Comprehensive Economic Partnership Agreement (CEPA) serves as a catalyst for diversifying India's trade basket beyond traditional commodities.

**Proposal for new design of border fencing under consideration of Centre: BSF IG - The Hind** — GS3 › security › border_management ✅
- Why: BSF IG Aloke Kumar Chakraborty stated that the Ministry of Home Affairs is considering a proposal for a new design of barbed wire fencing along the India-Bangladesh border to replace aging infrastructure.
- [data_fact] India-Bangladesh international border length: 4,096 km
- [data_fact] Tripura's share of the India-Bangladesh border: 856 km
- [institution] Ministry of Home Affairs (MHA) is the nodal ministry for border fencing proposals
- [person_post] Aloke Kumar Chakraborty is the Inspector General (IG) of the BSF Tripura Frontier
- Q: Discuss the significance of robust border infrastructure and joint patrolling mechanisms in managing trans-border crimes and ensuring regional security between India and Bangladesh.

**What is going wrong in Tamil Nadu’s SIR? | Focus Tamil Nadu - The Hindu** — GS2 › polity › elections ✅
- Why: Reports indicate that Tamil Nadu’s Special Intensive Revision (SIR) process is facing operational failures, potentially leading to the deletion of genuine voters due to unrealistic deadlines and confusing documentation.
- [institution] The Election Commission of India (ECI) is the body responsible for overseeing the Special Intensive Revision (SIR) of voter lists.
- [data_fact] The SIR process in Tamil Nadu is currently facing risks of deleting lakhs of genuine voters.
- Q: Critically analyze the challenges in maintaining the integrity of electoral rolls during intensive revision processes and suggest measures to ensure inclusive voter participation.

**PM Modi calls Sri Lankan President to offer continued support with cyclone relief - The Hi** — GS2 › ir › neighbourhood ✅
- Why: Prime Minister Narendra Modi assured Sri Lankan President Anura Kumara Dissanayake of continued support under Operation Sagar Bandhu to assist in cyclone relief and rehabilitation.
- [data_fact] Operation Sagar Bandhu: India's specific relief and rescue operation for Sri Lanka following Cyclone Ditwah.
- [data_fact] India has handed over 53 tonnes of relief material to Sri Lanka as of December 1, 2025.
- [place] Cyclone Ditwah: The specific cyclone causing devastation in Sri Lanka.
- [data_fact] Rescued nationals: Included citizens from Sri Lanka, India, Germany, Slovenia, UK, South Africa, Poland, Belarus, Iran, Australia, Pakistan, and Bangladesh.
- [data_fact] NDRF teams were dispatched to Sri Lanka on November 29 for search and rescue operations.
- Q: Examine the significance of India's 'Neighborhood First' policy in the context of its Humanitarian Assistance and Disaster Relief (HADR) operations in South Asia.

**EC tells Supreme Court Centre’s citizenship scrutiny powers are limited - The Hindu** — GS2 › polity › constitution ✅
- Why: The Election Commission of India (ECI) submitted an affidavit to the Supreme Court arguing that the Centre's exclusive jurisdiction over citizenship is limited to the voluntary acquisition of foreign citizenship, not th…
- [constitution] Article 326: Specifies Indian citizenship as a constitutional precondition for entry into the voter list.
- [constitution] Article 324: Empowers the Election Commission to supervise and control the conduct of elections.
- [act_bill] Section 9 of the Citizenship Act, 1955: Vests the Centre's authority to determine the termination of citizenship due to voluntary acquisition of foreign citizenship.
- [data_fact] The ECI submitted a 184-page affidavit in the Special Intensive Revision (SIR) case.
- Q: Examine the constitutional balance between the Election Commission's plenary powers under Article 324 and the Union Government's exclusive jurisdiction over citizenship matters.

**Putin is coming to India in December 2025: Which other Russian presidents visited India, i** — GS2 › ir › bilateral ✅
- Why: The Ministry of External Affairs announced that President Vladimir Putin will visit India from 4 to 5 December 2025 to attend the India-Russia Annual Summit.
- [data_fact] Putin's visit to India is scheduled for 4 to 5 December 2025.
- [person_post] Vladimir Putin was sworn in as President of Russia on 7 May 2000.
- [data_fact] The 2025 visit marks the India-Russia Annual Summit.
- [data_fact] The relationship is defined as a Special and Privileged Strategic Partnership.
- Q: Discuss the evolution of the Special and Privileged Strategic Partnership between India and Russia in the context of contemporary global security challenges.

**Jakarta overtakes Tokyo as world’s most populous city, according to UN | Indonesia | The G** — GS1 › society › urbanisation ✅
- Why: The UN Department of Economic and Social Affairs released the World Urbanisation Prospects 2025 report, which re-ranks Jakarta as the world's most populous city due to new methodology.
- [data_fact] Jakarta population: 42 million
- [data_fact] Dhaka population: 37 million
- [data_fact] Tokyo population (megalopolis): 33 million
- [data_fact] Number of megacities (10m+ inhabitants) projected to reach 33 by 2025
- Q: Discuss the challenges and opportunities associated with the rapid growth of megacities in Asia, with special reference to urban planning and social equity.

**Over 68% SIR enumeration forms digitised: ECI - The Hindu** — GS2 › polity › elections ✅
- Why: The Election Commission of India (ECI) reported that over 68% of enumeration forms for the Special Intensive Revision (SIR) of electoral rolls have been digitised across 12 States and UTs.
- [data_fact] 34,86,60,338 enumeration forms (over 68% of existing electors) have been digitised as of November 27, 2025.
- [data_fact] Lakshadweep and Goa are among the leading states in digitisation with 99.9% and 89.77% respectively.
- [data_fact] Uttar Pradesh and Kerala are the lagging states with 47.59% and 55% digitisation respectively.
- [institution] Booth-level officers (BLOs) are responsible for collecting filled-in forms and uploading data to the ECI website via dedicated apps.
- Q: Discuss the significance of digitising electoral rolls in ensuring the integrity of the democratic process and the challenges faced in achieving universal coverage.

