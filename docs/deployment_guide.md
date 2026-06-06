# 🚀 Simple Project Deployment Guide (For Everyone)

Welcome! This guide is written in plain English. You do **not** need to be a software developer or system administrator to deploy this project. If you can click buttons and copy-paste text, you can get this AI Document Intelligence platform up and running in **under 10 minutes**!

---

## 📋 Table of Contents
1. [What is this project?](#1-what-is-this-project)
2. [Step 1: Get Your Free AI Keys (Groq)](#step-1-get-your-free-ai-keys-groq)
3. [Step 2: Setup Your Free Vector Database (Pinecone)](#step-2-setup-your-free-vector-database-pinecone)
4. [Step 3: Deploy the Backend "Brain" (Render)](#step-3-deploy-the-backend-brain-render)
5. [Step 4: Deploy the Frontend "Interface" (Vercel)](#step-4-deploy-the-frontend-interface-vercel)
6. [Step 5: Connect the Interface to the Brain](#step-5-connect-the-interface-to-the-brain)
7. [Step 6: Test Your App!](#step-6-test-your-app)
8. [Troubleshooting (When things don't work)](#troubleshooting-when-things-dont-work)
9. [Optional: Local Computer Setup](#optional-local-computer-setup)

---

## 1. What is this project?

This application allows you to upload text files, PDFs (including scanned papers), and images, and ask questions about them. An AI reads the files and answers your questions instantly, showing you exactly where it found the information.

It is split into three main parts:
1. **The Database (Pinecone):** Stores the text of your files so the system can search through them.
2. **The Backend (The Brain):** The Python code that processes your files and talks to the AI model.
3. **The Frontend (The Interface):** The web page you see in your browser with upload buttons and search boxes.

---

## Step 1: Get Your Free AI Keys (Groq)

The brain of this application uses **Groq**, a service that runs AI models very quickly. You need to get an API key (a secret password) so the application can talk to the AI.

1. Go to the [Groq Console](https://console.groq.com/).
2. Log in (you can create a free account using your Google/GitHub account or email).
3. In the left sidebar, click on **API Keys**.
4. Click **Create API Key**.
5. Give it a name (e.g., `My-Search-System`), click **Create**, and **copy the long key** (it starts with `gsk_`). 
   > ⚠️ **Important:** Copy this key and save it somewhere safe. You will not be able to view it again once you close the window.

---

## Step 2: Setup Your Free Vector Database (Pinecone)

Instead of saving uploaded files on a single computer, the application uses **Pinecone** to store file data securely in the cloud.

1. Go to [Pinecone](https://www.pinecone.io/) and click **Sign Up Free**.
2. Log in using your email or Google account.
3. Click the **Create Index** button.
4. **Configure your Index settings exactly like this:**
   * **Index Name:** `semantic-search-index`
   * **Dimensions:** `384` *(Must be exactly 384)*
   * **Metric:** `cosine`
   * **Project Type:** Select `Serverless`. Choose the cloud region closest to you.
5. Click **Create Index**.
6. Once created, copy the **Index Name** (`semantic-search-index`).
7. In the left sidebar, click **API Keys** and **copy the API Key** (a long string of numbers and letters).

---

## Step 3: Deploy the Backend "Brain" (Render)

We will host the python backend code on **Render**, a platform that runs web applications in the cloud for free.

1. Create a free account on [Render](https://render.com) using your GitHub account.
2. Once logged in, click the blue **New +** button in the top right, and select **Web Service**.
3. Choose **Build and deploy from a Git repository**, click **Next**, and connect your GitHub repository `Semantic-Search-System`.
4. **Configure your deployment settings exactly like this:**
   * **Name:** `my-semantic-search-api`
   * **Region:** Choose the region closest to you (e.g., *Oregon (US West)*).
   * **Branch:** `main`
   * **Root Directory:** *Leave this blank/empty.*
   * **Runtime:** Select `Docker`.
5. Scroll down to the **Environment Variables** section and click **Add Environment Variable** to add these three keys:
   1. **GROQ_API_KEY**: *Paste your Groq API Key (from Step 1, starts with `gsk_`)*.
   2. **PINECONE_API_KEY**: *Paste your Pinecone API Key (from Step 2)*.
   3. **PINECONE_INDEX_NAME**: `semantic-search-index` *(Must match your index name)*.
6. Scroll down to the **Disk** section to set up temporary database storage (for relationship graphs):
   * Click **Add Disk**.
   * **Name:** `database-disk`
   * **Mount Path:** `/app/backend/data`
   * **Size:** `10 GiB` (free tier is fine).
7. Click **Create Web Service** at the bottom of the page.

Render will now build your container. This will take **3–4 minutes** because it is downloading and caching the AI models inside the server. 
Once finished, you will see a green **Live** badge, and a public URL at the top left (e.g., `https://my-semantic-search-api.onrender.com`). **Copy this URL.**

---

## Step 4: Deploy the Frontend "Interface" (Vercel)

We will host the web interface on **Vercel**, which is free and loads web pages instantly.

1. Create a free account on [Vercel](https://vercel.com) using your GitHub account.
2. Click **Add New** > **Project**.
3. Locate your `Semantic-Search-System` repository and click **Import**.
4. **Configure your project settings:**
   * **Framework Preset:** Select `Other`.
   * **Root Directory:** Click Edit and select the **`frontend`** folder.
5. Click **Deploy**.
6. Within 30 seconds, Vercel will complete the deploy. Click on the screenshot preview of your website to open your live web interface!

---

## Step 5: Connect the Interface to the Brain

Right now, your frontend interface doesn't know where the backend API brain is running. We need to connect them.

1. Open your code repository on GitHub or your local computer.
2. Open the file named **`frontend/index.html`** in a text editor or on GitHub.
3. Locate line **308** (inside the `<script>` tag near the bottom of the file):
   ```javascript
   // ── Set your Render backend URL here ───────────────────────────────────────
   const BACKEND_URL = ""; 
   ```
4. Paste the Render URL you copied in **Step 3** inside the quotes:
   ```javascript
   const BACKEND_URL = "https://my-semantic-search-api.onrender.com"; 
   ```
5. Save the file and commit the changes (Vercel will automatically detect this change and redeploy your website within a few seconds).

---

## Step 6: Test Your App!

1. Open your Vercel website link (or `http://localhost:5000` if running locally).
2. Click **Drag & drop files here** or browse to select your files (you can upload multiple files, up to 75 at once).
3. Click the blue **Upload Files** button. 
   * *A progress bar will fill up as files are uploaded in rapid succession.*
   * *Below the upload card, a **Live status dashboard** will appear showing a list of your files. Each file displays its current status (⏳ Queued → 🔄 Processing → ✅ Done / ❌ Failed).*
   * *As the backend processes files sequentially in a background queue, you will see statuses update dynamically. Text PDFs take 5–15 seconds; scanned or image-based PDFs take 20–60 seconds.*
4. Type a question about the uploaded files in the **Ask a Question** box and click **Search**.
5. The AI will write the response answer, list the source document references (citations) below, and indicate whether a Knowledge Graph-expanded context walk was performed!

---

## Troubleshooting (When things don't work)

### 🔴 The upload is stuck on "Uploading..." or returns a network error
* **Root Cause:** Your Vercel frontend is calling an incorrect or dead backend URL.
* **Fix:** Verify you updated line 308 in `frontend/index.html` with your exact Render URL (ensure it starts with `https://` and has no typos).

### 🔴 The search answers return "⚠️ Groq API key is not set"
* **Root Cause:** Your Render environment variable is missing or incorrect.
* **Fix:** Go to your Render Web Service dashboard, click **Environment**, check the `GROQ_API_KEY` spelling, paste your Groq key again, and save changes.

### 🔴 The upload fails with connection error to Pinecone
* **Root Cause:** Incorrect Pinecone credentials or your index isn't ready.
* **Fix:** Verify you set `PINECONE_API_KEY` and `PINECONE_INDEX_NAME` correctly on the Render environment dashboard, and make sure your index name is typed exactly as shown in the Pinecone console.

### 🔴 The first query takes 30-50 seconds to load
* **Root Cause:** Render puts free services to sleep after 15 minutes of inactivity. When you call the website, it takes a moment to boot the container back up.
* **Fix:** This is normal for the free tier. Once awake, subsequent questions will respond in under 2 seconds.

---

## Optional: Local Computer Setup

If you want to run the project locally on your own computer instead of in the cloud:

1. **Required tools:** Install Python 3.10+, [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki), and [Poppler](https://blog.alivate.com.au/poppler-windows/) on your system.
2. **Download code & install libraries:**
   Open your command line terminal (PowerShell or Terminal) and run:
   ```bash
   git clone https://github.com/sakshamsaxena22/Semantic-Search-System.git
   cd Semantic-Search-System
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```
3. **Configure Settings:**
   Create a file named `.env` in the root folder and add your key:
   ```env
   GROQ_API_KEY=gsk_your_actual_key_here
   ```
4. **Run Server:**
   ```bash
   python backend/app/main.py
   ```
5. Open your web browser and go to **[http://localhost:5000](http://localhost:5000)**.
