import os
import joblib
import random
import requests
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
# from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# from utils.DeepSeek import DeepSeekEmbeddings

# Constants
TARGET_DIM=768
PROJECTION_DIR = "projection_models"
os.makedirs(PROJECTION_DIR, exist_ok=True)
SAMPLE_TEXTS = [
    "Vegan Diet Video Guide English - YashMind Home Courses Data Leads Ebooks Reels Course Login Login Register 0₹ 0 HomeCoursesVegan Diet Video Guide English Vegan Diet Video Guide English ₹ 8,768 Sold by Y k Ask owner Enroll Now CASH BACK $ 30 Step-by-Step Vegan Guide 10 High-Quality Video Modules Healthy Ethical Living Plant-Based Nutrition Meal Planning Exclusive eBook Audio Guide Mind Map Cheat Sheet Included 60-Day Money-Back Guarantee Created by Mayadunna Category Courses Cashback Description You Will Learn Additional information Reviews 0 CASH BACK Please follow the steps below to receive your cashback 1 Enter your name. 2 Upload your invoice. 3 Provide your PayPal ID for purchaser outside India or UPI ID for purchaser in India to avail cashback payment. 4 Write a review of the purchased product on YashMind. Ensure that the name in the review matches the invoice name and you entered for cashback too, otherwise the cashback will not be processed",
    ". 4 Write a review of the purchased product on YashMind. Ensure that the name in the review matches the invoice name and you entered for cashback too, otherwise the cashback will not be processed. Note - Cashback will be proceed within 7 days from your invoice submission. Cashback status will be sent to your registered mail ID. If you have any question regarding cashback so Please send us on supportyashmind.in To Avail CashBack Please Click Here to fill the Cashback Form httpsforms.glettt4aEZaYgLr8jZk8 Description Vegan Diet The Complete Video Guide to a Cruelty-Free Lifestyle is your ultimate step-by-step guide to transitioning into a healthy, ethical, and sustainable vegan lifestyle. Whether youre a beginner or looking to refine your plant-based journey, this program provides everything you needfrom meal planning and nutrition to habit-building and sustainable living practices",
    "Home - YashMind Home Courses Data Leads Ebooks Reels Course Login Login Register 0₹ 0 Welcome to YashMind The Ultimate Digital Products Marketplace Explore, Buy, and Sell Premium Digital Creations, Step into a dynamic digital marketplace where passion meets innovation. Discover expertly crafted digital products from creators around the globe and unlock endless possibilities to fuel your digital journey Get Free Offer Explore By Categories You are guaranteed to find something thats right for you Explore categories Courses 70 items Ebooks 100 items Templates 180 items Booksand Magazines 200 items Transform Your Future with Expert-Led Courses Master the Skills You Need to Thrive in Todays World - 91 Artificial Intelligence Generative AI English Sold by ₹ 2,000 Original price was ₹ 2,000.₹ 180Current price is ₹ 180. Add to cart - 90 Artificial Intelligence Text to Image AI Course Hindi Sold by ₹ 3,000 Original price was ₹ 3,000.₹ 290Current price is ₹ 290",
    ". Whether youre a beginner or looking to refine your plant-based journey, this program provides everything you needfrom meal planning and nutrition to habit-building and sustainable living practices. With expert-led video training, youll learn the key differences between vegetarianism and veganism, how to stay healthy while living vegan, and how to incorporate exercise, hydration, and plant-based protein into your routine. Plus, youll receive exclusive bonuses, including an eBook, MP3 audio guide, cheat sheet, mind map, and resource guide to support your transition and success. For a limited-time offer of $99.95, you get instant access to this comprehensive, life-changing course You Will Learn The Vegan Lifestyle Why It Matters Understand the core principles of veganism and why its a transformative way of life. Vegetarianism vs. Veganism Learn the key differences and how to make informed choices about your diet and lifestyle",
    ". Vegetarianism vs. Veganism Learn the key differences and how to make informed choices about your diet and lifestyle. How to Stay Healthy While Living Vegan Discover essential plant-based nutrition tips to maintain energy, strength, and overall wellness. Meal Planning Food Preparation Gain access to practical meal plans and preparation tips to simplify your vegan journey. Breaking Old Habits Adopting New Ones Get strategies to overcome cravings, transition smoothly, and stay committed to a vegan lifestyle. The Importance of Plant-Based Protein Learn how to get enough protein from plant-based sources to maintain optimal health. Living Vegan Beyond Food Discover how veganism extends beyond diet to clothing, beauty products, and ethical consumer choices. Exercise Hydration for a Balanced Lifestyle Incorporate fitness and hydration habits to enhance your well-being",
    ". Vegetarianism vs. Veganism Learn the key differences and how to make informed choices about your diet and lifestyle. How to Stay Healthy While Living Vegan Discover essential plant-based nutrition tips to maintain energy, strength, and overall wellness. Meal Planning Food Preparation Gain access to practical meal plans and preparation tips to simplify your vegan journey. Breaking Old Habits Adopting New Ones Get strategies to overcome cravings, transition smoothly, and stay committed to a vegan lifestyle. The Importance of Plant-Based Protein Learn how to get enough protein from plant-based sources to maintain optimal health. Living Vegan Beyond Food Discover how veganism extends beyond diet to clothing, beauty products, and ethical consumer choices. Exercise Hydration for a Balanced Lifestyle Incorporate fitness and hydration habits to enhance your well-being",
    ". Be the first to review Vegan Diet Video Guide English Cancel replyYour email address will not be published. Required fields are marked Your Rating Rate Perfect Good Average Not that bad Very Poor Your Review Name Email Save my name, email, and website in this browser for the next time I comment. Vegan Diet Video Guide English Cashback Description You Will Learn Additional information Reviews 0 ₹ 8,768 Enroll Now Related Products - 91 Freelancer Course Hindi Sold by ₹ 2,000 Original price was ₹ 2,000.₹ 180Current price is ₹ 180. Add to cart - 87 YouTube Profit A Complete Guide English Sold by ₹ 2,000 Original price was ₹ 2,000.₹ 270Current price is ₹ 270. Add to cart - 89 Canva Pro Design Crouse Hindi Sold by ₹ 2,500 Original price was ₹ 2,500.₹ 280Current price is ₹ 280. Add to cart - 87 Youtube SEO Complete Course Hindi Sold by ₹ 2,000 Original price was ₹ 2,000.₹ 259Current price is ₹ 259",
    ". Add to cart - 89 Canva Pro Design Crouse Hindi Sold by ₹ 2,500 Original price was ₹ 2,500.₹ 280Current price is ₹ 280. Add to cart - 87 Youtube SEO Complete Course Hindi Sold by ₹ 2,000 Original price was ₹ 2,000.₹ 259Current price is ₹ 259. Add to cart - 90 The Non-fungible Token NFT Course English Sold by ₹ 3,000 Original price was ₹ 3,000.₹ 290Current price is ₹ 290. Add to cart YASHMIND, GLOBAL TRADE CENTRE, KHAMLA ROAD, DEO NAGAR, NAGPUR - 440015, MAHARASHTRA, INDIA About Us Contact Us Terms Conditions  Refund Policy Disclaimer Become a Seller NEWSLETTER Subscribe for tips, updates, and special offers YashMind is Registered Trademark of the PLAYBOSS GAMES PVT LTD. Copyright 2025 PLAYBOSS GAMES PRIVATE LIMITED.,",
    ". Copyright 2025 PLAYBOSS GAMES PRIVATE LIMITED., . USD EUR INR CNY IDR BRL PKR RUB JPY CHF KRW CAD AUD BDT Search for All categories B2B Christian Living Personal Growth Courses Ebooks Educational Learning Hospitality Reels Self-Improvement Uncategorized Log In Username Password Lost Password Remember me Login Dont have an account Sign Up Shopping cart",
    ". Add to cart - 90 Artificial Intelligence Text to Image AI Course Hindi Sold by ₹ 3,000 Original price was ₹ 3,000.₹ 290Current price is ₹ 290. Add to cart - 90 Artificial Intelligence Full Stack Web Development with AI Course Hindi Sold by ₹ 3,000 Original price was ₹ 3,000.₹ 290Current price is ₹ 290. Add to cart - 92 Courses StartUp Freelance Business Course English Sold by ₹ 2,500 Original price was ₹ 2,500.₹ 190Current price is ₹ 190. Add to cart Exclusive Data Leads Collection Grow Your Business with Verified and Targeted Leads - 90 Apparels B2B-Apparels-2K Leads Sold by ₹ 2,300 Original price was ₹ 2,300.₹ 230Current price is ₹ 230. Add to cart - 89 Architectural Designs B2B-Architectural Designs 1K Leads Sold by ₹ 1,000 Original price was ₹ 1,000.₹ 110Current price is ₹ 110. Add to cart - 91 Arts and Crafts B2B-Arts and Crafts-3K Leads Sold by ₹ 3,700 Original price was ₹ 3,700.₹ 350Current price is ₹ 350",
    ". Our platform is designed for flexibility, so you can fit learning into your lifestyle and achieve your goals on your terms. Start learning today What Our Customers say Connect your products with Reviews to get best results Uncategorized Review 1 YashMind is hands down the best digital marketplace Ive ever used. I recently purchased ... Uncategorized Review 2 I started my journey with YashMind a few months ago, and I cant believe how ... Uncategorized Review 3 The courses on YashMind are absolutely top-notch I recently completed a ... Join 25k Innovators and Dreamers in One Dynamic Space Your journey to digital mastery starts here. Connect, create, and thrive with the best in the industry. Explore top-notch courses, premium digital products, cutting-edge tools, and a vibrant communityall in one place"

    # E-commerce Product Listings
    "Wireless Bluetooth Headphones - Premium sound quality with 40hr battery life. Noise cancellation & built-in mic. Available in black/white. ₹2,999 (30% off). Free shipping on orders above ₹999.",
    "Organic Cotton T-Shirt - Breathable fabric, unisex fit. Made with 100% GOTS certified cotton. Sizes: S-XXL. Color options: navy, olive, charcoal. Price: ₹899. Sustainable packaging.",
    
    # Educational Content
    "Python for Beginners: Learn variables, loops, functions in 4 weeks. Includes 10 projects & certificate. Course duration: 20hrs video. Instructor: Dr. Smith (10yrs experience). Enrollment open now!",
    "The Science of Nutrition: Understand macros, micros & meal planning. Module 1 covers carbohydrates - their types, glycemic index, and role in metabolism. Downloadable worksheets included.",
    
    # Technical Documentation
    "API Error 401: Unauthorized access. Verify your authentication token is valid and included in the header. Token format: 'Bearer <your_jwt_token>'. Retry after regenerating tokens.",
    "To install the SDK: 'pip install package-name==2.3.1'. Requires Python 3.8+. For Linux, first run 'sudo apt-get install libssl-dev'. Check installation with 'package-name --version'.",
    
    # News Articles
    "Market Update: Sensex falls 450pts amid global recession fears. IT stocks hit hardest. Gold prices rise to ₹58,000/10gm. Experts advise diversified portfolio in current volatility.",
    "New Health Study: Walking 8k steps/day reduces cardiac risks by 40%. Research conducted on 10k participants over 5 years. 'Even short walks help' says lead researcher Dr. Lee.",
    
    # Social Media Content
    "Just launched our new productivity app! 🚀 Track habits, set goals & analyze trends. Limited-time offer: 1yr premium for $29 (70% off). Download now: [link] #productivity #lifehacks",
    "Recipe: 3-ingredient banana pancakes 🥞→ 1 banana, 2 eggs, 1/4cup oats. Blend & cook on low heat. Top with honey & nuts. 15g protein per serving! Comment if you try it 👇",
    
    # Legal/Policy Text
    "Privacy Policy Update: We now encrypt all user data with AES-256. Data retention period reduced to 12 months. You may request deletion via [email] or account dashboard. Effective Jan 2025.",
    "Terms §4.3: User-generated content must not violate copyrights. By uploading, you grant us non-exclusive rights to display & modify content. DMCA complaints: legal@example.com",
    
    # Travel Content
    "Bali Travel Guide: Best season is May-Sept. Must-visit: Ubud temples, Nusa Penida cliffs. Avg hotel: $50/night. Local tip: Rent scooters for $5/day. Visa-free for 30days for Indians.",
    "Packing List for Himalayas: Thermal layers, waterproof boots, 60L backpack, portable charger. Altitude sickness pills recommended. Trek permits cost ₹1500/person from govt portal.",
    
    # Financial Advice
    "How to Save ₹1L/year: 1) Automate 15% salary to FD 2) Cut 3 cafe visits/month (saves ₹3600) 3) Use cashback apps for groceries. Track with our free budget template [link]",
    "Crypto Tax Guide India: 30% tax on profits. Must file even with losses. Exchanges report to IT dept. Save all transaction IDs. AY2025 deadline: July 31. Penalty: 1%/month delay.",
    
    # Health & Wellness
    "Yoga for Back Pain: Try these 5 asanas daily → Cat-Cow (2mins), Child's Pose (1min), Sphinx (30sec). Avoid forward bends if acute pain. Consult doctor before starting new routines.",
    "Mental Health Check: Rate your sleep, energy & mood 1-10 daily. <5 for 3+ days? Take our free anxiety test. Helpline: 1800-123-456 (24/7). You're not alone 💙",
    
    # Tech Reviews
    "iPhone 16 Pro Review: New titanium frame, 5x optical zoom. Battery lasts 22hrs video. Downsides: Heavy (221g), no charger included. Best for photographers. Rating: 4.5/5",
    "Windows 12 First Look: AI-powered Copilot, redesigned Start menu. Requires 8GB RAM minimum. Release date: Nov 2025. Upgrade guide for enterprises: [link] #TechNews",
    
    # Real Estate
    "2BHK Apartment in Bangalore: 1200sqft, gated society. ₹85L. Amenities: pool, gym, 24/7 security. 5km from MG Road. Loan approval available. Contact: 98765XXXXX (no brokers).",
    "Commercial Space Mumbai: 800sqft retail unit, Andheri East. ₹3.5L/month. Footfall: 2000/day. Ideal for cafes/fashion. Lease terms: 3yr min. Visit by appointment only.",
    
    # Job Postings
    "Hiring Senior Data Scientist: 5+ yrs ML experience. Skills: Python, TensorFlow, AWS. Remote OK. Salary: ₹35-45L/yr + ESOPs. Apply: careers@company.com (Ref: DS-2025)",
    "Internship: Content Writer (3months). Work on blogs & social media. Stipend: ₹15k/month + certificate. Requirements: English fluency, SEO basics. Send samples to hr@example.org",
    
    # Event Listings
    "Webinar: AI in Healthcare (June 25, 3PM IST). Speakers from Mayo Clinic & Google Health. Free registration → [link] Topics: Diagnosis tools, ethics, future trends. Q&A session included.",
    "Music Festival Delhi: 20+ artists, 3 stages. Nov 15-17. Early bird tickets ₹1999 (till Aug 31). Venue: NSIC Grounds. No plastic policy. Lineup announcement next week! #DelhiEvents",
    
    # Automotive
    "2025 Tesla Model 3 Update: 640km range, 0-100kmph in 3.1s. Price: ₹65L ex-showroom. New feature: Smart Summon via app. Test drives available in Mumbai/Delhi/Bangalore.",
    "Bike Maintenance Tips: Change engine oil every 5000km. Check tire pressure weekly. Chain lubrication monthly. Winter care: Use antifreeze coolant. Save ₹5000/yr on repairs.",
    
    # Food & Beverage
    "Cold Brew Coffee Recipe: Coarse grind 50g beans, steep in 500ml water for 18hrs fridge. Filter & dilute 1:1 with milk. Serve over ice. Caffeine content: 200mg/serving.",
    "Wine Pairing Guide: Chardonnay → grilled fish. Merlot → pasta. Champagne → appetizers. Serving temp: 10-12°C for whites, 16-18°C for reds. Always hold glass by stem.",
    
    # Parenting
    "Newborn Essentials Checklist: 10 onesies, 200 diapers, nasal aspirator, baby carrier. Pro tip: Buy diapers in bulk online (saves 30%). Hospital bag must-pack: nursing pillow.",
    "Teen Phone Rules: 1) No devices after 10PM 2) Social media = 1hr/day 3) Location sharing ON. Use parental control apps like Family Link. Discuss digital safety monthly.",
    
    # DIY/Crafts
    "DIY Wall Art: Paint canvas with acrylics, then press leaves for texture. Seal with mod podge. Cost: ₹500 (vs ₹3000 store-bought). Great weekend project! Full tutorial [link]",
    "Macrame Plant Hanger Tutorial: Need 5m cotton rope & 2 rings. Knots: square, spiral. Time: 2hrs beginner. Hang 30cm below ceiling for best look. Makes great gifts!",
    
  # 🛍️ E-commerce Product Listings
  "Smart LED TV 43-inch – 4K UHD resolution, Dolby Audio, Android OS with built-in Chromecast. Voice remote included. Apps: Netflix, Prime Video, YouTube. Wall mount kit free. ₹23,499 (MRP ₹29,999). No-cost EMI for 6 months. 1-year warranty + free installation. Limited stock available.",
  "Eco-Friendly Yoga Mat – Non-slip, 6mm thick, made from TPE material. Sweat-resistant and odor-free. Size: 183x61cm. Comes with carry strap. Ideal for hot yoga, Pilates, floor workouts. Price: ₹1,199. Ships in 24hrs. Returns accepted within 10 days.",

  # 📚 Educational Content
  "Master JavaScript in 30 Days – Covers ES6+, DOM, async programming, APIs & frameworks. Access 80+ lessons, 20 challenges, real-time code editor. Weekly live sessions with industry mentors. ₹999 one-time fee. Certificate + community support included.",
  "Graphic Design Basics – Learn Canva, Figma & Adobe Express. Create logos, social posts, flyers. Suitable for beginners. 10 hours of content, templates included. Certificate of completion. Free trial available for 7 days. Rated 4.8/5 by 1,200 learners.",

  # ⚙️ Technical Documentation
  "To authenticate with our API, send a POST request to `/auth/token` with your client ID & secret. The response returns a JWT valid for 1 hour. Include it in headers as `Authorization: Bearer <token>`. Rate limit: 1000 requests/hour. Errors return JSON with `error_code` and `message`.",
  "To deploy to production, run `npm run build` followed by `pm2 start server.js`. Ensure environment variables are set: `NODE_ENV=production`, `PORT=3000`, `DB_URI=...`. Monitor logs with `pm2 logs`. Auto-restart on crash is enabled by default.",

  # 📰 News
  "Budget 2025 Highlights: Income tax slabs remain unchanged. ₹1.2L crore allocated to green energy. MSME credit guarantee extended. Digital India gets ₹10,000 crore boost. New AI R&D mission launched. Stock markets responded positively post-announcement.",
  "India clinches series win vs Australia: 3-1. Rohit Sharma scores century in final ODI. Bumrah picks 4/38. Player of the Series: Kuldeep Yadav. Next: T20I series begins on Jan 20. Tickets live now on official BCCI app.",

  # 📱 Social Media / App Copy
  "Meet Notely – your next-gen note app 📝 with markdown support, cloud sync & offline access. Organize notes into boards, add checklists & tags. Android + iOS. Lifetime plan ₹499. Join 25K+ users. #NoteApp #ProductivityTools",
  "🏋️‍♂️ Challenge Alert: 30 days of home workouts – no gym needed! Follow our guided plan with videos, track progress, and win rewards. Tag @fitpulseapp to get featured. Starts Sept 1. Free for all users. #GetFitAtHome",

  # 📜 Legal/Policy
  "Cookie Policy: We use cookies to personalize content, analyze traffic & deliver ads. You may accept, reject, or customize via the Settings panel. Cookies expire in 30 days unless manually cleared. For more info, visit our Privacy Policy section.",
  "Terms Update: New section §6.1 prohibits scraping of site content using bots or scripts. Violations will result in IP bans. Users are responsible for securing credentials. Changes effective Sept 10, 2025. Questions? Email support@example.com",

  # 🌍 Travel Guides
  "Europe Backpacking Tips: Use Eurail pass for budget travel across 30+ countries. Stay in hostels (avg €20/night). Best apps: Omio, Hostelworld, Google Translate. Travel insurance is essential. Carry a power bank & universal adapter. Best months: May–Sept.",
  "Thailand on a Budget: Visit Bangkok, Chiang Mai, Krabi. Street food meals from ₹100. Stay in guesthouses for ₹500/night. Night markets, temples & beaches. Visa-on-arrival for Indians. Local SIM costs ₹400 for 7 days. Avoid scams at tourist hotspots.",

  # 💰 Personal Finance
  "Building Credit Score: Pay bills on time, maintain <30% credit usage, and avoid frequent loan inquiries. Check your CIBIL score monthly. Use secured credit card if you're a beginner. A score >750 improves loan approval chances. Monitor via RBI-approved portals.",
  "Investing ₹5,000/month: SIP in index funds, emergency fund in liquid fund, optional gold via SGB. Avoid ULIPs and high-commission plans. Review portfolio every 6 months. Learn compounding via calculators. Read: ‘Let’s Talk Money’ by Monika Halan.",

  # 🧘 Wellness
  "Meditation for Beginners: Start with 5 mins daily. Use apps like Headspace, Insight Timer. Focus on breath, gently return when distracted. Best time: morning or post-work. Don’t aim for perfection—just consistency. Benefits: reduced stress, better sleep, improved focus.",
  "Hydration Tips: Drink 2–3L/day. Add lemon or cucumber for flavor. Avoid sugary drinks. Use a 1L bottle to track. Signs of dehydration: fatigue, dark urine, headaches. Coconut water is a great electrolyte source. Limit coffee to 2 cups/day max.",

  # 🧪 Product/Tech Reviews
  "OnePlus Pad Review: 11.6” LCD 144Hz, MediaTek Dimensity 9000, 8GB RAM, 9510mAh battery. Pros: fluid UI, stereo speakers, magnetic keyboard support. Cons: no LTE option. Price: ₹39,999. Great for students & creators. Alternatives: Galaxy Tab S7 FE.",
  "MacBook Air M3 Preview: New 3nm chip, up to 18hr battery, 13” & 15” variants. Fanless design. 2x Thunderbolt ports, MagSafe charging. Price starts ₹1,14,999. Ships Oct 2025. Best for students, travelers, devs. Base model: 256GB SSD, 8GB RAM.",

  # 🏠 Real Estate
  "1RK Studio in Pune – Baner locality. 450 sqft, ₹45L. Fully furnished, balcony, modular kitchen. Gated society, gym, lift. Loan approved by SBI/HDFC. Maintenance: ₹1,500/month. Ideal for singles, students. Broker-free listing. Contact owner: 98765XXXXX.",
  "Plot for Sale – 1200 sqft in Whitefield, Bangalore. ₹68L. Clear titles, gated community. 15 mins from ITPL. Water, electricity, drainage ready. Ideal for residential or rental investment. Schedule a site visit: Mon–Sat, 10AM–5PM. RERA approved.",

  # 👔 Job Listings
  "Hiring Frontend Developer (React) – 3+ yrs experience, knowledge of TypeScript, Redux, Tailwind. Remote or Bangalore. Salary ₹15–20L. Perks: MacBook, L&D budget, flexible hours. Apply with portfolio: jobs@xyztech.in (Ref: FE-2025).",
  "Campus Ambassador Program – Promote our ed-tech platform on campus. Get goodies, LOR, and earn ₹10k+/month via referrals. 4hrs/week commitment. Open to all universities. Selection via task + 1 interview. Deadline: Sept 10. Apply at [link].",

  # 🎫 Events
  "Startup Demo Day – Sept 20, 5PM IST. 10+ startups pitch to investors. Jury: Blume, Accel, Sequoia reps. Free virtual attendance. Q&A and networking rooms included. Register at startupweek.in. Winners get ₹5L grants + mentorship. #IndianStartups",
  "Art Fair Mumbai – Oct 12–14, BKC Ground. Featuring 100+ artists across India. Entry: ₹150/day. Workshops: calligraphy, acrylics, pottery. Food stalls & live music on all days. Eco-friendly materials only. Tickets live now on Insider.",

  # 🚗 Automotive
  "Kia EV6 GT Line Review – 708km range (ARAI), 0–100 in 5.2s, dual motor AWD, ADAS level 2. Interior: 12.3” curved displays, ventilated seats, 14-speaker Meridian sound. ₹60L on-road. Pros: performance, design. Cons: limited service centers.",
  "Car Maintenance Checklist: 1) Change oil every 10K km 2) Rotate tires every 7.5K km 3) Clean AC filter bi-monthly 4) Brake pads inspection every 15K km. Keep documents & insurance renewed. Use OBD2 scanner for diagnostics. Avoid engine idling >5min.",

  # 🍲 Food & Recipes
  "Chickpea Salad Bowl: Mix boiled chickpeas, diced cucumber, cherry tomatoes, onion, lemon juice, olive oil, pepper & salt. Optional: feta, mint. High protein, fiber-rich, vegan. Prep time: 10 mins. Store up to 2 days in fridge. Great for meal prep.",
  "South Indian Filter Coffee: Boil water & milk in 1:1 ratio. Add brewed decoction from percolator (20g coffee, 100ml hot water). Pour back-and-forth to froth. Serve hot in tumbler-dabara set. Authentic taste with jaggery instead of sugar.",

  # 👶 Parenting
  "Baby Sleep Schedule: 0–3m: 16–18 hrs/day, 4–6m: 14–16 hrs. Set consistent bedtime, use white noise. Avoid screen exposure before sleep. Bedtime routine: feed, change, rock. Signs of sleep regression: frequent waking, fussiness. Consult if persists.",
  "Toddler Tantrums: Stay calm, use simple words. Set clear boundaries & give limited choices. Praise good behavior. Avoid shouting. Use distraction for <3yrs. Create safe space for expression. Avoid screen time during/after meltdowns.",

  # 🛠️ DIY/Crafts
  "DIY Floating Shelf: Use 18mm plywood, cut to 24” x 8”. Sand edges, apply stain/paint. Use hidden bracket mounts for clean look. Tools: drill, level, screws. Weight limit: ~10kg. Time: 1hr. Great for books, planters. Cost under ₹600.",
  "Mason Jar Lights: Clean jars, insert battery LED string lights, decorate with jute rope & labels. Hang using wall hooks or place on tables. Great for balcony, events. Safe & low voltage. ₹200 per jar DIY cost. Time: 30 mins per piece.",
]



# 1. Projection Model Management
def train_or_load_projection_models() -> Dict[str, Any]:
    """Load cached models or train new ones"""
    models = {}
    model_dir = Path("projection_models")
    
    for tool in ["DeepSeek","Gemini"]:
        model_path = model_dir / f"{tool.lower()}_model.joblib"
        
        if model_path.exists():
            models[tool] = joblib.load(model_path)
        else:
            models[tool] = _train_projection_model(tool)  # Saves automatically
            
    return models

def _get_diverse_samples() -> List[str]:
    """Returns 1000+ diverse text samples from multiple sources"""
    print("\n[DEBUG] Gathering diverse samples...")
    samples = []
    
    # 1. Existing samples
    if SAMPLE_TEXTS:
        print(f"[DEBUG] Adding {len(SAMPLE_TEXTS)} existing samples")
        samples.extend(SAMPLE_TEXTS)
    
    # 2. Wikipedia snippets (expanded)
    try:
        print("[DEBUG] Fetching Wikipedia samples...")
        wiki_titles = [
            "Machine_learning", "Artificial_intelligence", "Python_(programming_language)", 
            "Nutrition", "Data_science", "Renewable_energy", "Blockchain", "Quantum_computing",
            "Natural_language_processing", "Computer_vision", "Deep_learning", "Statistics",
            "Mathematics", "Physics", "Chemistry", "Biology", "Economics", "Psychology",
            "History_of_science", "Philosophy", "Literature", "Art", "Music", "Architecture"
        ]
        
        for title in wiki_titles:
            print(f"[DEBUG] Fetching Wikipedia: {title}")
            response = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                headers={"User-Agent": "Embedding-Training/1.0"},
                timeout=10
            )
            if response.status_code == 200:
                samples.append(response.json()["extract"])
                # Also get the full page for more content
                full_page = requests.get(
                    f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&titles={title}&explaintext=1&format=json",
                    headers={"User-Agent": "Embedding-Training/1.0"},
                    timeout=10
                )
                if full_page.status_code == 200:
                    pages = full_page.json().get('query', {}).get('pages', {})
                    for page in pages.values():
                        if 'extract' in page:
                            # Split into paragraphs
                            paragraphs = [p for p in page['extract'].split('\n') if len(p.split()) > 30]
                            samples.extend(paragraphs[:10])  # Take first 10 good paragraphs
        print(f"[DEBUG] Added Wikipedia samples (total now: {len(samples)})")
    except Exception as e:
        print(f"[ERROR] Wikipedia API failed: {str(e)}")

    # 3. Synthetic samples (expanded)
    print("[DEBUG] Generating synthetic samples...")
    synthetic_topics = [
        "The impact of AI on healthcare diagnostics",
        "How blockchain technology enables decentralized finance",
        "Best practices for sustainable agriculture",
        "The evolution of quantum computing architectures",
        "Modern techniques in natural language processing",
        "Advances in computer vision applications",
        "The role of big data in business decision making",
        "Ethical considerations in machine learning",
        "Cloud computing infrastructure optimization",
        "Neural network architectures for time series prediction"
    ]
    
    for topic in synthetic_topics:
        for _ in range(100):  # Increased from 40 to 100
            # Generate variations of each topic
            samples.append(
                f"{topic} {random.choice(['has significantly', 'might potentially', 'is expected to'])} "
                f"{random.choice(['transform', 'disrupt', 'revolutionize'])} "
                f"{random.choice(['industry standards', 'traditional approaches', 'existing paradigms'])} "
                f"through {random.choice(['innovative', 'novel', 'groundbreaking'])} "
                f"{random.choice(['methodologies', 'techniques', 'frameworks'])}."
            )
    print(f"[DEBUG] Added synthetic samples (total now: {len(samples)})")

    # 4. Domain-specific augmentation (expanded)
    print("[DEBUG] Generating domain-specific samples...")
    domains = ["e-commerce", "healthcare", "finance", "education", "technology", 
              "manufacturing", "retail", "telecommunications", "transportation", "energy"]
    templates = [
        "10 ways {domain} is changing {aspect}",
        "The complete guide to {concept} in {domain}",
        "How we implemented {solution} for our {domain} platform",
        "{domain} trends in {year} and what they mean for {stakeholders}",
        "Case study: Applying {methodology} in {domain} to solve {problem}",
        "The future of {domain} and its impact on {sector}",
        "{domain} best practices for {objective}",
        "Comparing {approach1} and {approach2} in {domain} applications"
    ]
    
    for _ in range(500):  # Increased from 200 to 500
        template = random.choice(templates)
        domain = random.choice(domains)
        samples.append(
            template.format(
                domain=domain,
                aspect=random.choice(["customer experience", "regulatory compliance", "profit margins"]),
                concept=f"{random.choice(['AI', 'blockchain', 'IoT'])} integration",
                solution=f"{random.choice(['predictive', 'adaptive', 'scalable'])} {random.choice(['analytics', 'model', 'framework'])}",
                year=random.choice(["2023", "2024", "2025"]),
                stakeholders=random.choice(["businesses", "consumers", "regulators"]),
                methodology=random.choice(["agile", "lean", "six sigma"]),
                problem=random.choice(["cost reduction", "efficiency improvement", "quality control"]),
                sector=random.choice(["global markets", "local economies", "supply chains"]),
                objective=random.choice(["digital transformation", "process optimization", "risk management"]),
                approach1=random.choice(["traditional", "machine learning", "heuristic"]),
                approach2=random.choice(["modern", "deep learning", "statistical"])
            )
        )
    print(f"[DEBUG] Added domain-specific samples (total now: {len(samples)})")

    # 5. Add news headlines (simulated)
    print("[DEBUG] Adding news headline samples...")
    news_categories = ["business", "technology", "science", "health", "entertainment"]
    for _ in range(200):
        category = random.choice(news_categories)
        samples.append(
            f"{random.choice(['Breaking', 'Latest', 'Exclusive'])} {category} news: "
            f"{random.choice(['Researchers', 'Scientists', 'A team'])} "
            f"{random.choice(['discover', 'develop', 'create'])} "
            f"{random.choice(['new', 'innovative', 'groundbreaking'])} "
            f"{random.choice(['method', 'technology', 'approach'])} "
            f"for {random.choice(['treating diseases', 'improving efficiency', 'reducing costs'])}"
        )
    print(f"[DEBUG] Added news samples (total now: {len(samples)})")

    # Final processing - modified to retain more samples
    print("[DEBUG] Filtering samples...")
    final_samples = []
    for sample in samples:
        words = sample.split()
        word_count = len(words)
        
        # Keep samples with at least 8 words (reduced from 15)
        if word_count >= 8:
            # For short samples (8-30 words), combine with another short sample
            if 8 <= word_count <= 30:
                # Find another short sample to combine with
                for other_sample in samples:
                    other_words = other_sample.split()
                    if 8 <= len(other_words) <= 30 and sample != other_sample:
                        combined = f"{sample} {other_sample}"
                        if len(combined.split()) <= 200:  # Ensure combined isn't too long
                            final_samples.append(combined)
                            break
                else:
                    # If no pair found, keep the original short sample
                    final_samples.append(sample)
            else:
                # For longer samples, just truncate if needed
                final_samples.append(' '.join(words[:200]))
    
    # Deduplicate while preserving order
    seen = set()
    final_samples = [x for x in final_samples if not (x in seen or seen.add(x))]
    
    print(f"[DEBUG] Final sample count: {len(final_samples)}")
    random.shuffle(final_samples)
    return final_samples[:1000] if len(final_samples) > 1000 else final_samples

def _train_projection_model(tool: str) -> Dict[str, Any]:
    """Train, validate, and save projection models with debug prints"""
    print(f"\n[DEBUG] Training projection model for {tool}")
    
    model_dir = Path("projection_models")
    model_dir.mkdir(exist_ok=True)
    
    print("[DEBUG] Gathering training samples...")
    sample_texts = _get_diverse_samples()
    print(f"[DEBUG] Using {len(sample_texts)} samples for training")

    print("[DEBUG] Getting native embeddings...")
    emb = _get_native_embeddings(tool)
    print("[DEBUG] Generating embedding vectors...")
    native_vecs = np.array([emb.embed_query(text) for text in sample_texts])
    
    print(f"[DEBUG] Native vectors shape: {native_vecs.shape}")
    if native_vecs.shape[1] < TARGET_DIM:
        error_msg = f"Cannot project {tool} from {native_vecs.shape[1]}D to {TARGET_DIM}D"
        print(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    print("[DEBUG] Fitting StandardScaler...")
    scaler = StandardScaler()
    scaled_vecs = scaler.fit_transform(native_vecs)
    
    print(f"[DEBUG] Fitting PCA with {TARGET_DIM} components...")
    pca = PCA(n_components=TARGET_DIM, whiten=True, random_state=42)
    pca.fit(scaled_vecs)
    
    variance = sum(pca.explained_variance_ratio_)
    print(f"[DEBUG] PCA variance captured: {variance:.1%}")
    if variance < 0.9:
        print(f"[WARNING] Low variance capture for {tool}")

    model_path = model_dir / f"{tool.lower()}_model.joblib"
    print(f"[DEBUG] Saving model to {model_path}")
    joblib.dump({"scaler": scaler, "pca": pca}, model_path)
    
    print("[DEBUG] Model training complete")
    return {"scaler": scaler, "pca": pca}

def get_embeddings(tool: str, use_projection: bool = True):
    """Get embeddings with debug prints"""
    print(f"\n[DEBUG] Getting embeddings for {tool}")
    
    print("[DEBUG] Getting native embeddings...")
    native_emb = _get_native_embeddings(tool)
    
    if not use_projection or tool == "ChatGPT":
        print("[DEBUG] Returning native embeddings")
        return native_emb
    
    print("[DEBUG] Loading projection models...")
    models = train_or_load_projection_models()
    
    if tool not in models:
        error_msg = f"No projection model for {tool}"
        print(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    def projected_embed_query(text: str) -> list[float]:
        print(f"[DEBUG] Projecting embedding for text (length: {len(text)})")
        vec = np.array(native_emb.embed_query(text)).reshape(1, -1)
        scaled = models[tool]["scaler"].transform(vec)
        projected = models[tool]["pca"].transform(scaled)
        print(f"[DEBUG] Projected shape: {projected.shape}")
        return projected[0].tolist()
    
    print("[DEBUG] Returning projected embeddings")
    return type("ProjectedEmbeddings", (), {"embed_query": projected_embed_query})

def _get_native_embeddings(tool: str):
    print(f"\n[DEBUG] Getting native embeddings for {tool}")
    # if tool == "DeepSeek":
    #     print("[DEBUG] Using DeepSeek native embeddings")
    #     return DeepSeekEmbeddings(model_name="deepseek-embedding")
    if tool == "ChatGPT":
        print("[DEBUG] Using OpenAI embeddings")
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=TARGET_DIM,
            api_key=os.getenv("OPENAI_API_KEY"))
    elif tool == "Gemini" or tool == "DeepSeek":
        print("[DEBUG] Using Gemini embeddings")
        return GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=os.getenv("GOOGLE_API_KEY"))
    error_msg = f"Unsupported tool: {tool}"
    print(f"[ERROR] {error_msg}")
    raise ValueError(error_msg)