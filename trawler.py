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

# --- 3. PUBMED (ENTREZ) CONFIGURATION ---
Entrez.email = "rehabinapinch@gmail.com"
Entrez.api_key = PUBMED_KEY

# --- 4. TOPICS, FILTERS & PRIORITY AUTHORS ---
STUDY_TYPES = '(Meta-Analysis[pt] OR "Randomized Controlled Trial"[pt] OR "Systematic Review"[pt] OR "Clinical Trial"[pt] OR "Observational Study"[pt])'
NO_ANIMALS = 'NOT ("animals"[MeSH Terms] NOT "humans"[MeSH Terms])'
DATE_RANGE = '("2025/01/01"[PDAT] : "3000/12/31"[PDAT])'
LOCATIONS = 'AND (China[ad] OR Japan[ad] OR Europe[ad] OR "North America"[ad] OR USA[ad] OR Canada[ad])'

FILTERS = f"AND {STUDY_TYPES} {NO_ANIMALS} AND {DATE_RANGE} {LOCATIONS}"

# Added Priority Authors List
PRIORITY_AUTHORS = [
    "Zixin Zhang", "Zoe Yau Shan Chan", "Kim Hébert-Losier", 
    "Manuela Besomi", "Benoit Pairot de Fontenay", "Joachim Van Cant"
]

CATEGORIES = {
    "Running Injuries": f'"running"[ti] AND "injuries"[tiab] {FILTERS}',
    "Climbing Injuries": f'"climbing"[ti] AND "injuries"[tiab] {FILTERS}',
    "Physiotherapy General": f'"physiotherapy"[ti] OR "rehabilitation"[ti] AND "sports"[tiab] {FILTERS}',
    "Shoulder Rehab": f'"shoulder"[ti] AND ("rehabilitation"[tiab] OR "physiotherapy"[tiab]) {FILTERS}',
    "Knee Rehab": f'"knee"[ti] AND ("rehabilitation"[tiab] OR "physiotherapy"[tiab]) {FILTERS}'
}

# --- 5. FUNCTIONS ---
def get_pubmed_papers(query, max_results=10):
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
            abstract_text = medline.get('Abstract', {}).get('AbstractText', ['Not specified in abstract.'])[0]
            
            # Basic validation to avoid empty titles
            title = medline.get('ArticleTitle', 'No Title')
            if title == 'No Title': continue

            pmid = article['MedlineCitation']['PMID']
            doi_list = medline.get('ELocationID', [])
            clean_doi = next((str(item) for item in doi_list if str(item).startswith("10.")), "")
            final_link = f"https://doi.org/{clean_doi}" if clean_doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            papers.append({
                "title": title,
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
    # 1. TOKEN OPTIMIZATION: Use a stricter character limit (200 chars)
    # and check for common 'empty' phrases from PubMed.
    if not paper_text or "Not specified" in paper_text or len(paper_text) < 200:
        print(f"      ⏭️ Skipping Gemini: Abstract too short ({len(paper_text)} chars).")
        return {
            "methods": "Information not in abstract", 
            "findings": ["No abstract available for analysis."], 
            "implications": "Clinical details require full-text access."
        }

    # 2. THE PROMPT: Add a instruction to be brief to save output tokens
    prompt = f"""
    You are a Sports Scientist. Analyze this abstract concisely.
    Abstract: "{paper_text}"
    
    Rules:
    - If methods aren't clear, just write "Study design not stated".
    - Be extremely brief (max 15 words per field).
    
    Output strictly VALID JSON:
    {{
      "methods": "Short design & sample size",
      "findings": ["Point 1", "Point 2"],
      "implications": "One actionable clinical tip for a physiotherapist"
    }}
    """
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"methods": "Analysis Error", "findings": ["Error analyzing text"], "implications": "Check abstract"}

def load_existing_library():
    if os.path.exists('weekly_research.json'):
        with open('weekly_research.json', 'r') as f:
            try: return json.load(f)
            except: return {"last_updated": "", "papers": []}
    return {"last_updated": "", "papers": []}

# --- 6. MAIN LOOP ---
existing_data = load_existing_library()
existing_titles = [p['title'] for p in existing_data['papers']]
new_papers_count = 0

print("🚀 Starting Priority Author Search...")
for author in PRIORITY_AUTHORS:
    author_query = f'("{author}"[Author]) AND {DATE_RANGE}'
    papers = get_pubmed_papers(author_query, max_results=5)
    for p in papers:
        if p['title'] not in existing_titles:
            print(f"      ⭐ Priority Found: {p['title'][:40]}...")
            time.sleep(10) # Author priority rate limit
            analysis = analyze_with_gemini(p['abstract'])
            existing_data['papers'].insert(0, {**p, **analysis, "category": "Priority Author"})
            existing_titles.append(p['title'])
            new_papers_count += 1

print("🚀 Starting Standard Category Search...")
for topic, query in CATEGORIES.items():
    print(f"   Searching: {topic}...")
    papers = get_pubmed_papers(query, max_results=10)
    for p in papers:
        if p['title'] in existing_titles:
            continue

        print(f"      ✨ Analyzing New: {p['title'][:40]}...")
        time.sleep(15)
        analysis = analyze_with_gemini(p['abstract'])
        existing_data['papers'].insert(0, {**p, **analysis, "category": topic})
        new_papers_count += 1

existing_data['last_updated'] = datetime.now().strftime("%B %d, %Y")
with open('weekly_research.json', 'w') as f:
    json.dump(existing_data, f, indent=4)

print(f"✅ Database updated! Added {new_papers_count} new papers.")
