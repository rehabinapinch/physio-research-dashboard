import os
import json
import time
from datetime import datetime
from Bio import Entrez
import google.generativeai as genai
from dotenv import load_dotenv

# --- 1. ENVIRONMENT SETUP ---
load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PUBMED_KEY = os.getenv("ENTREZ_API_KEY")

# --- 2. GEMINI CONFIGURATION ---
genai.configure(api_key=GEMINI_KEY, transport='rest')
model = genai.GenerativeModel('gemini-2.5-flash')

print("✅ System Ready. Testing Connection to Gemini...")
try:
    response = model.generate_content("Say 'Connected'")
    print(f"✅ Google says: {response.text}")
except Exception as e:
    print(f"❌ CONNECTION FAILED: {e}")

# --- 3. PUBMED (ENTREZ) CONFIGURATION ---
Entrez.email = "rehabinapinch@gmail.com" 
Entrez.api_key = PUBMED_KEY 

# --- 4. TOPICS & FILTERS ---
STUDY_TYPES = '(Meta-Analysis[pt] OR "Randomized Controlled Trial"[pt] OR "Systematic Review"[pt] OR "Clinical Trial"[pt] OR "Observational Study"[pt])'
NO_ANIMALS = 'NOT ("animals"[MeSH Terms] NOT "humans"[MeSH Terms])'
DATE_RANGE = '("2025/01/01"[PDAT] : "3000/12/31"[PDAT])'
FILTERS = f"AND {STUDY_TYPES} {NO_ANIMALS} AND {DATE_RANGE}"

CATEGORIES = {
    "Running Injuries": f'"running"[ti] AND "injuries"[tiab] {FILTERS}',
    "Climbing Injuries": f'"climbing"[ti] AND "injuries"[tiab] {FILTERS}',
    "Physiotherapy General": f'"physiotherapy"[ti] OR "rehabilitation"[ti] AND "sports"[tiab] {FILTERS}',
    "Shoulder Rehab": f'"shoulder"[ti] AND ("rehabilitation"[tiab] OR "physiotherapy"[tiab]) {FILTERS}',
    "Knee Rehab": f'"knee"[ti] AND ("rehabilitation"[tiab] OR "physiotherapy"[tiab]) {FILTERS}'
}

# --- 5. FUNCTIONS ---
def get_pubmed_papers(query, max_results=2):
    try:
        handle = Entrez.esearch(db="pubmed", term=query, sort="date", retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        
        if not record["IdList"]: return []
        
        ids = record["IdList"]
        handle = Entrez.efetch(db="pubmed", id=ids, retmode="xml")
        details = Entrez.read(handle)
        handle.close()
        
        papers = []
        for article in details['PubmedArticle']:
            medline = article['MedlineCitation']['Article']
            abstract_text = medline.get('Abstract', {}).get('AbstractText', ['No Abstract Available'])[0]
            
            pmid = article['MedlineCitation']['PMID']
            doi_list = medline.get('ELocationID', [])
            clean_doi = ""
            for item in doi_list:
                if str(item).startswith("10."): 
                    clean_doi = str(item)
                    break
            final_link = f"https://doi.org/{clean_doi}" if clean_doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            papers.append({
                "title": medline.get('ArticleTitle', 'No Title'),
                "authors": medline.get('AuthorList', [{'LastName': 'Unknown'}])[0]['LastName'] + " et al.",
                "journal": medline.get('Journal', {}).get('Title', 'N/A'),
                "abstract": str(abstract_text),
                "link": final_link, 
                "year": medline.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {}).get('Year', '2025')
            })
        return papers
    except Exception as e:
        print(f"⚠️ PubMed Error: {e}")
        return []

def analyze_with_gemini(paper_text):
    prompt = f"""
    You are a Sports Scientist. Analyze this abstract.
    Abstract: "{paper_text}"
    
    Output strictly VALID JSON with these fields:
    - "methods": Briefly state study design and sample size (e.g., "Prospective Cohort, n=121").
    - "stats": Extract HARD DATA. Look for P-values (p=), Confidence Intervals (95% CI), Odds Ratios (OR), or Effect Sizes. Never use the label "Qualitative" if numbers are present. If absolutely NO numbers exist, write "Descriptive Data Only".
    - "findings": 2-3 bullet points. MUST include specific numbers/percentages if mentioned in the text.
    - "implications": One actionable clinical tip for a physiotherapist.
    """
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"\n❌ GEMINI ERROR: {e}")
        return {"methods": "Analysis Error", "findings": ["Error analyzing text"], "implications": "Check abstract", "stats": "N/A"}

def load_existing_library():
    if os.path.exists('weekly_research.json'):
        with open('weekly_research.json', 'r') as f:
            try:
                return json.load(f)
            except:
                return {"last_updated": "", "papers": []}
    return {"last_updated": "", "papers": []}

# --- 6. MAIN LOOP ---
existing_data = load_existing_library()
existing_titles = [p['title'] for p in existing_data['papers']]
new_papers_count = 0

print("🚀 Starting Search (Scientific Mode)...")

for topic, query in CATEGORIES.items():
    print(f"   Searching: {topic}...")
    papers = get_pubmed_papers(query, max_results=2) 
    for p in papers:
        if p['title'] in existing_titles:
            print(f"      ⏩ Skipping Duplicate: {p['title'][:20]}...")
            continue
            
        print(f"      ✨ Analyzing New: {p['title'][:20]}...")
        analysis = analyze_with_gemini(p['abstract'])
        
        existing_data['papers'].insert(0, {**p, **analysis, "category": topic})
        new_papers_count += 1
        time.sleep(1)

existing_data['last_updated'] = datetime.now().strftime("%B %d, %Y")

with open('weekly_research.json', 'w') as f:
    json.dump(existing_data, f, indent=4)

print(f"✅ Done! Added {new_papers_count} papers to weekly_research.json.")