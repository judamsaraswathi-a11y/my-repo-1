
import sys
import streamlit as st
import chromadb
import pandas as pd
from google import genai
from dotenv import load_dotenv
import os

st.set_page_config(
    page_title="Study Assistant Test",
    layout="centered"
)

st.title("AI-Powered Study Assistant")
st.subheader("Environment Testing")

st.write("Python Version:", sys.version)
st.write("Streamlit Version:", st.__version__)
st.write("ChromaDB Version:", chromadb.__version__)
st.write("Pandas Version:", pd.__version__)

st.divider()

# Test package imports
st.success("Streamlit imported successfully")
st.success("ChromaDB imported successfully")
st.success("Pandas imported successfully")
st.success("Gemini SDK imported successfully")

# Test API key loading
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    st.success("Gemini API key loaded from .env")
else:
    st.error("Gemini API key not found")

# Test ChromaDB connection
try:
    client = chromadb.PersistentClient(path="./chroma_db")
    collections = client.list_collections()

    st.success("ChromaDB connection successful")

    st.write("Available collections:")

    for collection in collections:
        st.write(collection.name)

except Exception as error:
    st.error(f"ChromaDB Error: {error}")

st.divider()

st.info("Environment testing completed.")
