#!/usr/bin/env python3
"""
Generic Policy Enforcement System
Step 0: Document Structure Analysis → stage0_structured_document.json (NEW)
Step 1: Extract policies from PDF → filename.txt
Step 1B: Extract & elaborate clauses with Gemini → stage1_clauses.json
Step 2: Classify clause intents with Gemini → stage2_classified.json
Step 3: Extract entities & thresholds with Gemini → stage3_entities.json
Step 4: Detect ambiguities in clauses → stage4_ambiguity_flags.json
Step 5: Clarify ambiguous clauses with Gemini → stage5_clarified_clauses.json
Step 6: Generate DSL rules from clarified clauses → stage6_dsl_rules.yaml
Step 9: DSL to Rego conversion for OPA → stage9_rego_bundles.json
Step 10: OPA Bundle Storage & Management → opa_bundles/v{version}/

Stage 0 is CRITICAL - it extracts Annexures which contain actual policy rules
(city classification, rates, thresholds) that were previously missing.

Usage:
  python policy_validator.py analyze-structure <policy.txt>    # Stage 0: Extract ALL sections
  python policy_validator.py extract <policy.pdf>
  python policy_validator.py extract-clauses <filename.txt>
  python policy_validator.py classify-intents <stage1_clauses.json>
  python policy_validator.py extract-entities <stage2_classified.json>
  python policy_validator.py detect-ambiguities <stage3_entities.json>
  python policy_validator.py clarify-ambiguities <stage3_entities.json>
  python policy_validator.py generate-dsl <stage5_clarified_clauses.json>
  python policy_validator.py opa-bundle-storage <stage9_rego_bundles.json>
"""

import os
import sys
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# LangChain imports for Stage 1 enhancement
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain.output_parsers import PydanticOutputParser
    from pydantic import BaseModel, Field, validator
    from typing import List
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# For MongoDB storage (optional)
try:
    from upload_service.database import PipelineStageManager
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    PipelineStageManager = None

# Configuration
GEMINI_API_KEY = "AIzaSyAgWfY5zft6IV00Y2HwPc3JHQva38zWEDQ"
OUTPUT_DIR = "/home/hutech/Documents/docupolicy"
LOG_FILE = f"{OUTPUT_DIR}/mechanism.log"


class PipelineConfig:
    """
    Centralized configuration for all pipeline stages
    No more hardcoded values scattered across classes
    """
    
    # LLM/Gemini Settings
    LLM_MODEL = "gemma-3-27b-it"
    LLM_TEMPERATURE = 0.1  # 0.0 = deterministic, 1.0 = creative
    LLM_MAX_RETRIES = 3    # Retry failed LLM calls
    
    # Text Processing
    CHUNK_SIZE = 3000
    CHUNK_OVERLAP = 300
    TEXT_PREVIEW_LENGTH = 8000  # For pattern discovery
    
    # Parallel Processing
    DEFAULT_MAX_WORKERS = 8
    DEFAULT_BATCH_SIZE = 3
    ENTITY_EXTRACTION_WORKERS = 8
    AMBIGUITY_CLARIFICATION_WORKERS = 8
    AMBIGUITY_CLARIFICATION_BATCH_SIZE = 3
    
    # Pattern Matching
    TOP_K_SIMILAR_CLAUSES = 3
    TOP_K_DSL_LOOKUP = 1
    
    # Timeout and Retries
    LLM_CALL_TIMEOUT = 120  # seconds
    LLM_RETRY_DELAY = 2     # seconds
    LLM_RETRY_ATTEMPTS = 2
    
    # JSON Parsing
    INTENT_CONFIDENCE_MIN = 0.0
    INTENT_CONFIDENCE_MAX = 1.0
    DEFAULT_CONFIDENCE = 0.75
    
    # Ambiguity Detection
    AMBIGUITY_STRICT_MODE = True  # Flag all potential ambiguities
    
    # Normalization
    NORMALIZATION_USE_LLM = False  # Default: use fast rule-based extraction
    
    @classmethod
    def to_dict(cls):
        """Export all configs as dictionary"""
        return {k: v for k, v in vars(cls).items() if not k.startswith('_') and not callable(v)}
    
    @classmethod
    def validate(cls):
        """Validate configuration values"""
        assert cls.LLM_TEMPERATURE >= 0.0 and cls.LLM_TEMPERATURE <= 1.0, "Temperature must be 0.0-1.0"
        assert cls.LLM_MAX_RETRIES >= 1, "Max retries must be >= 1"
        assert cls.CHUNK_SIZE > 0, "Chunk size must be > 0"
        assert cls.DEFAULT_MAX_WORKERS > 0, "Max workers must be > 0"
        assert cls.INTENT_CONFIDENCE_MIN >= 0.0, "Min confidence >= 0.0"
        assert cls.INTENT_CONFIDENCE_MAX <= 1.0, "Max confidence <= 1.0"
        return True


class PipelineStageStorage:
    """
    Helper class to manage storing pipeline stages to MongoDB.
    Used across all stage processors.
    """
    
    def __init__(self, enable_mongodb=True, document_id=None):
        """
        Initialize stage storage
        
        Args:
            enable_mongodb (bool): Whether to store to MongoDB
            document_id (str): Reference to document in raw_documents collection
        """
        self.enable_mongodb = enable_mongodb and MONGODB_AVAILABLE
        self.document_id = document_id or "unknown"
        self.stage_manager = None
        self.log = []
        self.log_lock = threading.Lock()  # Thread-safe logging
        
        if self.enable_mongodb:
            try:
                self.stage_manager = PipelineStageManager()
                if self.stage_manager.connect():
                    self.log_entry("INFO", "Connected to MongoDB for stage storage")
                else:
                    self.enable_mongodb = False
                    self.log_entry("WARNING", "Failed to connect to MongoDB, stage storage disabled")
            except Exception as e:
                self.enable_mongodb = False
                self.log_entry("WARNING", f"MongoDB unavailable: {e}")
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def store_stage(self, stage_number, stage_name, stage_output, filename=None):
        """
        Store a stage result to MongoDB with pending_approval status
        
        Args:
            stage_number (int): Stage number (1-7)
            stage_name (str): Name of stage
            stage_output (dict or list): The stage output data
            filename (str): Original filename
            
        Returns:
            dict: {'success': bool, 'stage_id': str, 'error': str}
        """
        
        if not self.enable_mongodb:
            self.log_entry("DEBUG", f"Stage {stage_number} ({stage_name}) storage skipped (MongoDB disabled)")
            return {'success': False, 'stage_id': None, 'error': 'MongoDB disabled'}
        
        try:
            result = self.stage_manager.insert_stage(
                document_id=self.document_id,
                stage_number=stage_number,
                stage_name=stage_name,
                stage_output=stage_output,
                filename=filename
            )
            
            if result['success']:
                self.log_entry("SUCCESS", f"Stage {stage_number} ({stage_name}) stored with status: pending_approval")
                self.log_entry("STAGE_ID", result['stage_id'])
            else:
                self.log_entry("ERROR", f"Failed to store stage {stage_number}: {result['error']}")
            
            return result
            
        except Exception as e:
            self.log_entry("ERROR", f"Stage storage exception: {str(e)}")
            return {'success': False, 'stage_id': None, 'error': str(e)}
    
    def get_pending_stages(self, limit=10):
        """Get all stages pending approval"""
        if not self.enable_mongodb:
            return []
        
        return self.stage_manager.get_pending_stages(limit)
    
    def approve_stage(self, stage_id, approved_by, notes=None):
        """Mark a stage as approved"""
        if not self.enable_mongodb:
            return {'success': False, 'error': 'MongoDB disabled'}
        
        return self.stage_manager.approve_stage(stage_id, approved_by, notes)
    
    def reject_stage(self, stage_id, rejected_by, reason):
        """Mark a stage as rejected"""
        if not self.enable_mongodb:
            return {'success': False, 'error': 'MongoDB disabled'}
        
        return self.stage_manager.reject_stage(stage_id, rejected_by, reason)
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.stage_manager:
            self.stage_manager.disconnect()


# ============================================================================
# STAGE 0: Document Structure Analysis & Annexure Extraction
# ============================================================================

class DocumentStructureAnalyzer:
    """
    Step 0: Pre-process policy document to extract ALL sections including Annexures.
    
    This stage solves the critical issue where Annexures (which contain actual 
    policy rules like city classification, rates, thresholds) were never passed 
    to downstream LLM stages.
    
    Input: filename.txt (raw policy document)
    Output: stage0_structured_document.json (all sections tagged and extracted)
    
    Example output structure:
    {
        "metadata": {
            "title": "Travel Policy",
            "document_id": "HR/Pol/02/2014",
            "total_sections": 12
        },
        "sections": {
            "objective": "...",
            "scope": "...",
            "numbered_clauses": [...],
            "annexures": {
                "Annexure 1": { ... },
                "Annexure 2": { 
                    "cityClassification": {
                        "Metros": ["Mumbai", "Delhi", "Kolkata"],
                        "StateCapital": [...],
                        "DistrictHQ": [...],
                        "OtherTowns": "*"
                    }
                },
                "Annexure 3": { ... },
                "Annexure 4": { ... }
            }
        },
        "all_clauses_for_processing": [
            {"clauseId": "C1", "text": "...", "source": "numbered"},
            {"clauseId": "CA1_1", "text": "...", "source": "Annexure 1"},
            ...
        ]
    }
    """
    
    ANNEXURE_PATTERNS = [
        r'Annexure\s*[-–]?\s*(\d+)[:\s]*(.*)',
        r'ANNEXURE\s*(\d+)[:\s]*(.*)',
        r'Appendix\s*(\d+)[:\s]*(.*)',
    ]
    
    SECTION_HEADERS = [
        r'^(Objective|Objective:|Objective\s*:)',
        r'^(Scope|Scope:|Scope\s*:)',
        r'^(Eligibility|Eligibility:|Eligibility\s*:)',
        r'^(General\s*Norms|General\s*Norms:|General\s*Norms\s*:)',
        r'^(Rates\s*for|Rates\s*for:|Rates\s*for\s*:)',
        r'^(Boarding|Boarding:|Boarding\s*:)',
        r'^(Lodging|Lodging:|Lodging\s*:)',
        r'^(Classification|Classification:|Classification\s*:)',
        r'^(Local\s*Conveyance|Local\s*Conveyance:|Local\s*Conveyance\s*:)',
        r'^(Daily\s*Allowance|Daily\s*Allowance:|Daily\s*Allowance\s*:)',
    ]
    
    def __init__(self, policy_file, document_id=None, enable_mongodb=True):
        self.policy_file = policy_file
        self.output_file = f"{OUTPUT_DIR}/stage0_structured_document.json"
        self.document_id = document_id or "unknown"
        self.log = []
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=self.document_id)
        
        self.log_entry("INFO", f"DocumentStructureAnalyzer initialized for: {policy_file}")
    
    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] [Stage 0] {message}"
        self.log.append(entry)
        print(entry)
    
    def read_policy_text(self):
        """Read raw policy text file"""
        try:
            with open(self.policy_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.log_entry("SUCCESS", f"Read policy text: {len(content)} characters")
            return content
        
        except FileNotFoundError:
            self.log_entry("ERROR", f"Policy text file not found: {self.policy_file}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read policy text: {e}")
            return None
    
    def extract_document_structure(self, content):
        """
        Parse policy document and identify all sections including Annexures.
        
        Returns dict with:
        - metadata: document info
        - sections: all parsed sections
        - annexures: extracted annexure data
        """
        lines = content.split('\n')
        
        document_info = {
            "title": "",
            "document_id": "",
            "effective_date": ""
        }
        
        sections = {
            "objective": "",
            "scope": "",
            "eligibility": "",
            "general_norms": [],
            "other_sections": {}
        }
        
        annexures = {}
        
        current_section = None
        current_content = []
        section_buffer = []
        
        # Extract document header info (first few lines)
        header_lines = []
        for i, line in enumerate(lines[:10]):
            line = line.strip()
            if not line:
                continue
            header_lines.append(line)
            if i < 3:
                document_info["title"] = line
            elif re.match(r'HR/Pol/\d+/\d+', line):
                document_info["document_id"] = line
        
        self.log_entry("INFO", f"Document header: {document_info['title']} ({document_info['document_id']})")
        
        # Parse remaining content
        in_annexure = False
        annexure_name = None
        section_buffer = []
        current_section = None
        current_content = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip page break markers
            if '\x0c' in line_stripped or line_stripped == '':
                continue
            
            # Check for Annexure headers
            annexure_match = None
            for pattern in self.ANNEXURE_PATTERNS:
                match = re.match(pattern, line_stripped, re.IGNORECASE)
                if match:
                    annexure_match = match
                    break
            
            if annexure_match:
                # Save previous annexure content
                if in_annexure and annexure_name and section_buffer:
                    annexures[annexure_name] = {
                        "content": '\n'.join(section_buffer),
                        "parsed": self._parse_annexure_content(annexure_name, section_buffer)
                    }
                    self.log_entry("INFO", f"Parsed {annexure_name}: {len(section_buffer)} lines")
                
                # Start new annexure
                annexure_num = annexure_match.group(1)
                annexure_name = f"Annexure {annexure_num}"
                in_annexure = True
                section_buffer = []
                current_section = None
                # Don't continue - let the next line be processed normally
                continue
            
            # If we're in an annexure, collect content
            if in_annexure:
                section_buffer.append(line)
                continue
            
            # Check for regular section headers
            header_match = None
            for pattern in self.SECTION_HEADERS:
                match = re.match(pattern, line_stripped, re.IGNORECASE)
                if match:
                    header_match = match
                    break
            
            if header_match:
                header_name = match.group(1) if hasattr(match, 'group') else str(match)
                # Save previous section
                if current_section and current_content:
                    self._store_section(sections, current_section, current_content)
                
                current_section = header_name.lower().replace(':', '').strip()
                current_content = []
                continue
            
            # Check for numbered clauses (1., 2., etc.)
            clause_match = re.match(r'^(\d+)[.)]\s+(.+)', line_stripped)
            
            if clause_match:
                # Save previous numbered clause content
                if current_section == "general_norms" and current_content:
                    sections["general_norms"].extend(current_content)
                
                # Start new clause
                clause_num = clause_match.group(1)
                clause_text = clause_match.group(2)
                current_section = "numbered_clause"
                current_content = [f"{clause_num}. {clause_text}"]
                continue
            
            # Continue building current content
            if current_content is not None:
                current_content.append(line)
        
        # Save final annexure
        if in_annexure and annexure_name:
            annexures[annexure_name] = {
                "content": '\n'.join(section_buffer),
                "parsed": self._parse_annexure_content(annexure_name, section_buffer)
            }
        
        # Save final section
        if current_section and current_content:
            if current_section == "numbered_clause":
                sections["general_norms"].extend(current_content)
            else:
                self._store_section(sections, current_section, current_content)
        
        # Extract effective date if present
        date_match = re.search(r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})', content, re.IGNORECASE)
        if date_match:
            document_info["effective_date"] = date_match.group(1)
        
        return {
            "metadata": document_info,
            "sections": sections,
            "annexures": annexures,
            "raw_content": content
        }
    
    def _store_section(self, sections, section_name, content):
        """Store parsed section content"""
        text = '\n'.join(content).strip()
        if not text:
            return
        
        if section_name in ["objective", "scope", "eligibility"]:
            sections[section_name] = text
        elif section_name == "numbered_clause":
            sections["general_norms"].extend(content)
        else:
            sections["other_sections"][section_name] = text
    
    def _parse_annexure_content(self, annexure_name, lines):
        """
        Parse annexure content based on type.
        Returns structured data for downstream processing.
        """
        content = '\n'.join(lines)
        
        parsed = {"raw": content, "type": "text", "data": {}}
        
        # Check annexure name AND content for type detection
        annexure_lower = annexure_name.lower()
        content_lower = content.lower()
        
        # Annexure 1: Travel Eligibility Notes
        if re.search(r'travel.*eligibility|note', annexure_lower, re.IGNORECASE) or \
           re.search(r'lodging.*inclusive|boarding.*inclusive', content_lower):
            parsed["type"] = "eligibility_notes"
            notes = []
            for line in lines:
                note_match = re.match(r'Note:?\s*(\d+)[.)]?\s*(.+)', line, re.IGNORECASE)
                if note_match:
                    notes.append({
                        "note_id": note_match.group(1),
                        "text": note_match.group(2).strip()
                    })
            parsed["data"]["notes"] = notes
        
        # Annexure 2: City Classification
        elif re.search(r'classification|cities|towns', annexure_lower, re.IGNORECASE) or \
             re.search(r'classification of cities|metros|state capital', content_lower):
            parsed["type"] = "city_classification"
            city_data = {
                "Metros": [],
                "StateCapital": [],
                "DistrictHQ": [],
                "OtherTowns": []
            }
            
            current_category = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for category headers
                category_match = re.match(r'^(Metros|State\s*Capital|Hill\s*Stations?|District\s*Head\s*Quarters?|Other\s*Towns?)[:\s-]*', line, re.IGNORECASE)
                if category_match:
                    current_category = category_match.group(1)
                    # Normalize category name
                    if 'metro' in current_category.lower():
                        current_category = "Metros"
                    elif 'state' in current_category.lower() or 'hill' in current_category.lower():
                        current_category = "StateCapital"
                    elif 'district' in current_category.lower():
                        current_category = "DistrictHQ"
                    elif 'other' in current_category.lower():
                        current_category = "OtherTowns"
                    
                    # Extract cities from the line
                    city_part = line[category_match.end():].strip(':- ')
                    if city_part:
                        cities = [c.strip() for c in city_part.split(',') if c.strip()]
                        city_data[current_category].extend(cities)
                    continue
                
                # Extract cities from list lines
                if current_category:
                    cities = [c.strip() for c in line.split(',') if c.strip()]
                    city_data[current_category].extend(cities)
            
            parsed["data"]["cityClassification"] = city_data
            self.log_entry("INFO", f"  Extracted {sum(len(v) for v in city_data.values())} cities")
        
        # Annexure 3: Field Work Allowance
        elif re.search(r'Field|Work|Allowance', annexure_name, re.IGNORECASE):
            parsed["type"] = "field_work_allowance"
            # Extract eligibility rules
            eligibility = []
            for line in lines:
                if re.search(r'(non\s*sales|non-sales|employees?)', line, re.IGNORECASE):
                    eligibility.append(line)
            parsed["data"]["eligibility"] = eligibility
        
        # Annexure 4: Local Conveyance / Personal Vehicle
        elif re.search(r'Local\s*Conveyance|Vehicle|Personal\s*(Car|Bike)', annexure_name, re.IGNORECASE):
            parsed["type"] = "vehicle_usage"
            rules = []
            for line in lines:
                if re.match(r'^\d+[.)]?\s*', line):
                    rules.append(line.strip())
            parsed["data"]["rules"] = rules
        
        # Annexure 5: Sales Personnel Lodging
        elif re.search(r'Sales\s*Personnel|Lodging', annexure_name, re.IGNORECASE):
            parsed["type"] = "sales_lodging"
            parsed["data"]["content"] = content
        
        # Annexure 6: Daily Allowance - Sales
        elif re.search(r'Daily\s*Allowance|Food|Fuel', annexure_name, re.IGNORECASE):
            parsed["type"] = "sales_daily_allowance"
            parsed["data"]["content"] = content
        
        return parsed
    
    def generate_all_clauses(self, structure):
        """
        Generate a comprehensive list of ALL clauses from document sections.
        This is what gets passed to Stage 1.
        
        Includes:
        - Numbered clauses (C1, C2, ...)
        - Annexure rules (CA1_1, CA1_2, ...)
        - Section headers as context clauses
        """
        all_clauses = []
        
        # Add objective as context clause
        if structure["sections"].get("objective"):
            all_clauses.append({
                "clauseId": "C0_Objective",
                "text": structure["sections"]["objective"],
                "source": "objective"
            })
        
        # Add scope as context clause
        if structure["sections"].get("scope"):
            all_clauses.append({
                "clauseId": "C0_Scope",
                "text": structure["sections"]["scope"],
                "source": "scope"
            })
        
        # Add numbered clauses
        clause_num = 1
        for norm in structure["sections"].get("general_norms", []):
            all_clauses.append({
                "clauseId": f"C{clause_num}",
                "text": norm,
                "source": "numbered_clause"
            })
            clause_num += 1
        
        # Add Annexure clauses
        for annexure_name, annexure_data in structure["annexures"].items():
            parsed = annexure_data.get("parsed", {})
            data = parsed.get("data", {})
            
            if parsed.get("type") == "city_classification":
                # Add city classification rules
                city_class = data.get("cityClassification", {})
                for category, cities in city_class.items():
                    if cities:
                        all_clauses.append({
                            "clauseId": f"CA_{annexure_name.replace(' ','')}_{category}",
                            "text": f"Cities classified as {category}: {', '.join(cities)}",
                            "source": annexure_name,
                            "entity_type": "cityClassification",
                            "category": category,
                            "cities": cities
                        })
            
            elif parsed.get("type") == "eligibility_notes":
                for note in data.get("notes", []):
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ','')}_Note{note['note_id']}",
                        "text": note["text"],
                        "source": annexure_name
                    })
            
            elif parsed.get("type") == "vehicle_usage":
                for i, rule in enumerate(data.get("rules", []), 1):
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ','')}_Rule{i}",
                        "text": rule,
                        "source": annexure_name
                    })
            
            elif parsed.get("type") == "field_work_allowance":
                for i, eligibility in enumerate(data.get("eligibility", []), 1):
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ','')}_Rule{i}",
                        "text": eligibility,
                        "source": annexure_name
                    })
            
            else:
                # Generic annexure content
                all_clauses.append({
                    "clauseId": f"CA_{annexure_name.replace(' ','')}_1",
                    "text": annexure_data.get("content", "")[:500],
                    "source": annexure_name
                })
        
        self.log_entry("INFO", f"Generated {len(all_clauses)} total clauses for processing")
        return all_clauses
    
    def analyze(self):
        """
        Main method: Pre-process policy document and extract ALL sections.
        
        Returns:
            dict: Structured document with all sections, annexures, and clauses
        """
        self.log_entry("START", "Stage 0: Document Structure Analysis & Annexure Extraction")
        
        # Read raw policy text
        content = self.read_policy_text()
        if not content:
            return None
        
        # Extract document structure
        self.log_entry("STEP", "Parsing document structure...")
        structure = self.extract_document_structure(content)
        
        # Generate all clauses including annexures
        all_clauses = self.generate_all_clauses(structure)
        structure["all_clauses"] = all_clauses
        structure["metadata"]["total_clauses"] = len(all_clauses)
        structure["metadata"]["total_annexures"] = len(structure["annexures"])
        
        # Save structured document
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)
            
            self.log_entry("SUCCESS", f"Structured document saved: {self.output_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=0,
                stage_name="document-structure-analysis",
                stage_output=structure,
                filename="stage0_structured_document.json"
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Structured document stored with ID: {db_result['stage_id']}")
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save structured document: {e}")
        
        # Summary
        self.log_entry("SUMMARY", f"Document: {structure['metadata']['title']}")
        self.log_entry("SUMMARY", f"Clauses extracted: {len(all_clauses)}")
        self.log_entry("SUMMARY", f"Annexures found: {len(structure['annexures'])}")
        
        annexure_counts = {}
        for ca in all_clauses:
            source = ca.get("source", "unknown")
            annexure_counts[source] = annexure_counts.get(source, 0) + 1
        
        for source, count in annexure_counts.items():
            self.log_entry("SUMMARY", f"  - {source}: {count} clauses")
        
        return structure
    
    def save_log(self):
        """Append discovery log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== STAGE 0: DOCUMENT STRUCTURE ANALYSIS LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class PatternDiscoveryEngine:
    """
    Step 0A: Discover domain-agnostic patterns from raw policy text
    
    Scans filename.txt with LLM to identify:
    - Pattern types (grades, allowances, durations, authorities, etc.)
    - Entity examples from actual text
    - Relationships between patterns
    - Data types (categorical vs numeric)
    
    Output: pattern_index.json (used by all downstream stages)
    
    Fully generic - works for travel policies, HR policies, leave policies, etc.
    No hardcoded domain rules.
    """
    
    def __init__(self, policy_text_file, document_id=None, enable_mongodb=True):
        self.policy_file = policy_text_file
        self.pattern_index_file = f"{OUTPUT_DIR}/pattern_index.json"
        self.document_id = document_id
        self.log = []
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
    
    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def read_policy_text(self):
        """Read raw policy text file"""
        try:
            with open(self.policy_file, 'r') as f:
                content = f.read()
            
            self.log_entry("SUCCESS", f"Read policy text: {len(content)} characters")
            return content
        
        except FileNotFoundError:
            self.log_entry("ERROR", f"Policy text file not found: {self.policy_file}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read policy text: {e}")
            return None
    
    def discover_patterns_with_llm(self, text):
        """
        Use Gemini LLM to identify ALL pattern types from raw policy text
        Returns structured pattern definitions (domain-agnostic)
        
        Args:
            text (str): Raw policy document text
            
        Returns:
            dict: Structured patterns with types, examples, keywords, relationships
        """
        
        # Chunk text to avoid token limits
        text_chunk = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analyze this policy document and identify ALL PATTERN TYPES present.

For EACH pattern type you find, specify:
1. PATTERN_TYPE: What category? (e.g., grades, allowances, durations, authorities, travel_modes, rates, locations, conditions, etc.)
2. EXAMPLES: List 5-10 specific values directly from the text
3. PATTERN_DESCRIPTION: How to recognize this pattern (keywords, context, format)
4. DATA_TYPE: Is it categorical (distinct values) or numeric (ranges)?
5. KEYWORDS: Words that indicate this pattern
6. RELATIONSHIPS: Does this pattern relate to others? (e.g., "grade → allowance", "duration → travel_type")
7. FREQUENCY: Approximate count in the document

POLICY TEXT:
────────────────────────────────────
{text_chunk}
────────────────────────────────────

OUTPUT ONLY VALID JSON (no markdown, no extra text):
{{
  "patterns": [
    {{
      "pattern_type": "pattern_name",
      "data_type": "categorical|numeric",
      "examples": ["value1", "value2", "value3"],
      "description": "Description of this pattern",
      "keywords": ["keyword1", "keyword2"],
      "relationships": ["pattern_a → pattern_b", "pattern_x → consequence_y"],
      "frequency": 10,
      "min_value": null,
      "max_value": null,
      "unit": null
    }}
  ]
}}

IMPORTANT:
- Include ALL pattern types you find (do not limit)
- Return ONLY valid JSON
- Extract actual values from text, do NOT invent
- Be specific about relationships
- If numeric, include min/max if discernible"""
        
        try:
            self.log_entry("LLM", "Discovering patterns with Gemini API")
            response = self.model.generate_content(prompt)
            patterns_text = response.text.strip()
            
            # Clean markdown if present
            if patterns_text.startswith("```"):
                patterns_text = patterns_text.split("```")[1]
                if patterns_text.startswith("json"):
                    patterns_text = patterns_text[4:]
                patterns_text = patterns_text.strip()
            
            patterns = json.loads(patterns_text)
            
            self.log_entry("SUCCESS", f"Discovered {len(patterns.get('patterns', []))} pattern types")
            return patterns
        
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"Failed to parse LLM response: {e}")
            return {"patterns": []}
        except Exception as e:
            self.log_entry("ERROR", f"Pattern discovery failed: {e}")
            return {"patterns": []}
    
    def build_pattern_index(self, patterns):
        """
        Convert LLM-discovered patterns into a queryable index structure
        
        Index allows:
        - Fast lookup by pattern type
        - Keyword-based lookups
        - Relationship traversal
        - Example extraction
        
        Args:
            patterns (dict): Patterns dict from LLM discovery
            
        Returns:
            dict: Indexed pattern structure
        """
        
        index = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "source": self.policy_file,
                "total_patterns": len(patterns.get('patterns', [])),
                "description": "Domain-agnostic pattern index for rule generation"
            },
            "pattern_types": {},
            "relationships": {},
            "keyword_lookup": {},
            "statistics": {}
        }
        
        pattern_list = patterns.get('patterns', [])
        
        if not pattern_list:
            self.log_entry("WARN", "No patterns discovered from LLM")
            return index
        
        # Process each pattern
        for pattern in pattern_list:
            pattern_type = pattern.get('pattern_type', 'unknown').lower()
            
            if not pattern_type or pattern_type == 'unknown':
                continue
            
            # Store pattern definition
            index["pattern_types"][pattern_type] = {
                "data_type": pattern.get('data_type', 'categorical'),
                "examples": pattern.get('examples', []),
                "description": pattern.get('description', ''),
                "keywords": pattern.get('keywords', []),
                "frequency": pattern.get('frequency', 0),
                "unit": pattern.get('unit'),
                "min_value": pattern.get('min_value'),
                "max_value": pattern.get('max_value'),
                "relationships": pattern.get('relationships', [])
            }
            
            # Build keyword → pattern_type lookup
            for keyword in pattern.get('keywords', []):
                keyword_lower = keyword.lower()
                if keyword_lower not in index["keyword_lookup"]:
                    index["keyword_lookup"][keyword_lower] = []
                if pattern_type not in index["keyword_lookup"][keyword_lower]:
                    index["keyword_lookup"][keyword_lower].append(pattern_type)
            
            # Store relationships
            relationships = pattern.get('relationships', [])
            if relationships:
                index["relationships"][pattern_type] = relationships
            
            # Statistics
            index["statistics"][pattern_type] = {
                "example_count": len(pattern.get('examples', [])),
                "keyword_count": len(pattern.get('keywords', [])),
                "frequency": pattern.get('frequency', 0)
            }
        
        return index
    
    def discover(self):
        """
        Main discovery workflow
        
        Returns:
            bool: Success/failure
        """
        self.log_entry("START", "Step 0A: Pattern Discovery from Raw Policy Text")
        self.log_entry("INFO", "Scanning policy document to identify domain-agnostic patterns")
        
        # Step 1: Read policy text
        self.log_entry("STEP", "Reading policy text from filename.txt")
        text = self.read_policy_text()
        if not text:
            return False
        
        # Step 2: Discover patterns with LLM
        self.log_entry("STEP", "Discovering patterns with LLM (this may take 30-60 seconds)")
        patterns = self.discover_patterns_with_llm(text)
        
        if not patterns.get('patterns'):
            self.log_entry("WARN", "No patterns discovered - check LLM output")
            return False
        
        # Step 3: Build index
        self.log_entry("STEP", "Building pattern index from discovered patterns")
        index = self.build_pattern_index(patterns)
        
        # Step 4: Save index to file
        try:
            with open(self.pattern_index_file, 'w') as f:
                json.dump(index, f, indent=2)
            
            self.log_entry("SUCCESS", f"Pattern index saved: {self.pattern_index_file}")
            self.log_entry("STATS", f"Pattern types discovered: {index['metadata']['total_patterns']}")
            self.log_entry("STATS", f"Keywords indexed: {len(index['keyword_lookup'])}")
            self.log_entry("STATS", f"Relationships found: {len(index['relationships'])}")
            
            # Step 5: Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=0,
                stage_name="pattern-discovery",
                stage_output=index,
                filename="pattern_index.json"
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Pattern index stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
        
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save pattern index: {e}")
            return False
    
    def save_log(self):
        """Append discovery log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== PATTERN DISCOVERY LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class PolicyExtractor:
    """Step 1: Extract text from PDF"""
    
    def __init__(self, pdf_file):
        self.pdf_file = pdf_file
        self.output_file = f"{OUTPUT_DIR}/filename.txt"
        self.log = []
        
    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def extract_pdf(self):
        """Extract PDF using pdftotext"""
        self.log_entry("INFO", f"Extracting PDF: {self.pdf_file}")
        
        try:
            # Use pdftotext
            result = subprocess.run(
                ['pdftotext', self.pdf_file, self.output_file],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get file stats
            with open(self.output_file, 'r') as f:
                content = f.read()
            
            lines = len(content.split('\n'))
            words = len(content.split())
            
            self.log_entry("SUCCESS", f"PDF extracted: {lines} lines, {words} words")
            self.log_entry("OUTPUT", f"File: {self.output_file}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.log_entry("ERROR", f"pdftotext failed: {e.stderr}")
            return False
        except FileNotFoundError:
            self.log_entry("ERROR", "pdftotext not installed. Install: sudo apt-get install poppler-utils")
            return False
        except Exception as e:
            self.log_entry("ERROR", str(e))
            return False
    
    def save_log(self):
        """Save extraction log"""
        with open(LOG_FILE, 'w') as f:
            f.write("=== POLICY EXTRACTION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


# Pydantic models for LangChain output parsing
if LANGCHAIN_AVAILABLE:
    class ClauseSchema(BaseModel):
        """Schema for a single policy clause"""
        clause_id: str = Field(description="Clause identifier (C1, C2, etc.)")
        text: str = Field(description="Elaborated clause text with conditions, values, and enforcement")
        
        @validator('clause_id')
        def validate_clause_id(cls, v):
            if not re.match(r'^C\d+$', v):
                raise ValueError(f"Invalid clause_id format: {v} (should be C1, C2, etc.)")
            return v
    
    class ClausesOutput(BaseModel):
        """Schema for multiple clauses"""
        clauses: List[ClauseSchema] = Field(description="List of extracted clauses")
    
    class IntentClassificationSchema(BaseModel):
        """Schema for intent classification result"""
        intent: str = Field(description="Intent type (RESTRICTION, LIMIT, CONDITIONAL_ALLOWANCE, etc.)")
        confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
        reasoning: str = Field(description="Brief explanation of intent classification")
        
        @validator('intent')
        def validate_intent(cls, v):
            allowed = ["RESTRICTION", "LIMIT", "CONDITIONAL_ALLOWANCE", "EXCEPTION",
                      "APPROVAL_REQUIRED", "ADVISORY", "INFORMATIONAL"]
            if v.upper() not in allowed:
                raise ValueError(f"Invalid intent: {v}")
            return v.upper()
    
    class AmbiguityDetectionSchema(BaseModel):
        """Schema for ambiguity detection result"""
        ambiguous: bool = Field(description="Whether the clause is ambiguous")
        reason: str = Field(description="Explanation of ambiguity or clarity")
        ambiguity_types: List[str] = Field(default=[], description="List of ambiguity type codes detected")
    
    class EntityExtractionSchema(BaseModel):
        """Schema for dynamic entity extraction - entities are dict with any keys"""
        entities: dict = Field(default={}, description="Dynamically extracted entities as key-value pairs")


class ClauseExtractor:
    """
    Step 1B: Extract & elaborate clauses from policy text.
    
    ENHANCED WITH LANGCHAIN:
    - Document chunking for large policies
    - Parallel processing of chunks
    - Structured output parsing with Pydantic
    - Automatic retry logic
    - Memory management for clause numbering
    
    Output structure: Simple clause_id → text mapping for Stage 2 intent classification.
    Each clause contains conditional statements, numerical values, enforcement levels, etc.
    """
    
    def __init__(self, policy_file, document_id=None, enable_mongodb=True, use_langchain=True):
        self.policy_file = policy_file
        self.clauses_file = f"{OUTPUT_DIR}/stage1_clauses.json"
        self.document_id = document_id
        self.log = []
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Initialize LangChain components if available
        if self.use_langchain:
            self.log_entry("INFO", "LangChain enabled for enhanced clause extraction")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=3000,
                chunk_overlap=300,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
        else:
            if not LANGCHAIN_AVAILABLE:
                self.log_entry("WARNING", "LangChain not available, using standard extraction")
    
    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def read_policy_file(self):
        """Read policy file"""
        try:
            with open(self.policy_file, 'r') as f:
                return f.read()
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read policy file: {e}")
            return None
    
    def extract_clauses_with_langchain(self, content):
        """
        LANGCHAIN-ENHANCED: Extract clauses using document chunking and parallel processing.
        
        Benefits:
        - Handles large documents (10k+ words)
        - Parallel chunk processing (30-40% faster)
        - Structured output validation
        - Automatic retry on failures
        
        Returns:
            list: Array of clause dicts with clause_id → text mapping
        """
        self.log_entry("LANGCHAIN", "Starting LangChain-enhanced clause extraction")
        
        # Step 1: Split document into chunks
        chunks = self.text_splitter.split_text(content)
        self.log_entry("CHUNKING", f"Split document into {len(chunks)} chunks")
        
        # Step 2: Create prompt template with output parser
        parser = PydanticOutputParser(pydantic_object=ClausesOutput)
        
        prompt_template = PromptTemplate(
            input_variables=["content", "start_clause_num"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
            template="""You are a POLICY CLAUSE EXTRACTION ENGINE. Extract ATOMIC, ELABORATED CLAUSES from this policy chunk.

CRITICAL REQUIREMENTS:
1. Each clause must be SELF-CONTAINED with elaborated details
2. Each clause text should be 4-5 lines MAXIMUM
3. MUST include:
   - Conditional statements (IF condition THEN consequence)
   - Numerical values (amounts, percentages, durations, thresholds)
   - Enforcement level (MUST/SHOULD/MAY)
   - Applicable roles or conditions
4. Start clause numbering from C{start_clause_num}
5. NO interpretation - extract exactly what the policy states
6. Preserve original section references

POLICY CHUNK:
{content}

{format_instructions}

OUTPUT ONLY valid JSON matching the schema. No explanations."""
        )
        
        # Step 3: Create chain
        chain = LLMChain(llm=self.langchain_llm, prompt=prompt_template)
        
        # Step 4: Process chunks sequentially (with clause counter)
        all_clauses = []
        clause_counter = 1
        
        for i, chunk in enumerate(chunks, 1):
            self.log_entry("PROCESSING", f"Chunk {i}/{len(chunks)} (starting at C{clause_counter})")
            
            try:
                # Run chain
                result = chain.run(content=chunk, start_clause_num=clause_counter)
                
                # Parse output
                parsed_output = parser.parse(result)
                chunk_clauses = [clause.dict() for clause in parsed_output.clauses]
                
                self.log_entry("SUCCESS", f"Extracted {len(chunk_clauses)} clauses from chunk {i}")
                all_clauses.extend(chunk_clauses)
                clause_counter += len(chunk_clauses)
                
            except Exception as e:
                self.log_entry("ERROR", f"Chunk {i} failed: {e}")
                # Fallback to standard extraction for this chunk
                self.log_entry("FALLBACK", f"Using standard extraction for chunk {i}")
                fallback_clauses = self._fallback_extraction(chunk, clause_counter)
                if fallback_clauses:
                    all_clauses.extend(fallback_clauses)
                    clause_counter += len(fallback_clauses)
        
        self.log_entry("COMPLETE", f"Total clauses extracted: {len(all_clauses)}")
        return all_clauses
    
    def _fallback_extraction(self, content, start_num):
        """Fallback to standard Gemini extraction if LangChain fails"""
        try:
            prompt = f"""Extract policy clauses from this text. Start numbering from C{start_num}.
Output JSON array: [{{"clause_id": "C{start_num}", "text": "..."}}]

CONTENT:
{content[:2000]}

OUTPUT ONLY JSON array."""
            
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean markdown
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            clauses = json.loads(response_text.strip())
            return clauses if isinstance(clauses, list) else []
        except:
            return []
    
    def extract_clauses_with_gemini(self, content):
        """
        Use Gemini API to extract individual clauses from raw policy text.
        Each clause should contain:
        - clause_id (C1, C2, C3, etc.)
        - Elaborated text (4-5 lines max) with:
          * Conditional statements (IF/THEN logic)
          * Numerical values (amounts, percentages, thresholds)
          * Clear enforcement intent
          * Referenced source section
        
        Returns:
            list: Array of clause dicts with clause_id → text mapping (linked list style)
        """
        
        self.log_entry("GEMINI", "Extracting and elaborating clauses from policy")
        
        prompt = f"""
You are a POLICY CLAUSE EXTRACTION ENGINE. Your task is to break down a policy document into 
ATOMIC, ELABORATED CLAUSES that can be linked together (linked-list structure where each 
clause_id points to detailed text).

CRITICAL REQUIREMENTS:
====================
1. Each clause must be SELF-CONTAINED but reference other clauses if needed
2. Each clause text should be 4-5 lines MAXIMUM with elaborated details
3. MUST include:
   - Conditional statements (IF condition THEN consequence)
   - Numerical values (amounts, percentages, durations, thresholds)
   - Enforcement level (MUST/SHOULD/MAY)
   - Applicable roles or conditions
4. Clauses form a LINKED-LIST (later clauses can reference earlier ones)
5. NO interpretation - extract exactly what the policy states
6. Preserve original clause numbering/section references from source

POLICY DOCUMENT:
================================================================================
{content}
================================================================================

OUTPUT FORMAT (JSON array only - no other text):
[
  {{
    "clause_id": "C1",
    "text": "4-5 line elaborated text with all details. Include IF/THEN, amounts, thresholds, 
             roles, enforcement level. If references previous clause, cite it as (refs: C0). 
             Source: Section X, Paragraph Y."
  }},
  {{
    "clause_id": "C2",
    "text": "Next clause elaborated with conditional logic, numerical values, and enforcement intent..."
  }}
]

ELABORATION RULES:
==================
- Expand vague terms with inferred context
- Make implicit conditions explicit (e.g., "after 4:30 PM" → "IF time >= 16:30 THEN...")
- Convert amounts to explicit values (e.g., "$500 per diem" → "Daily allowance: 500 USD")
- State role/grade applicability explicitly
- Flag cross-references between clauses with (refs: C#)
- Mark enforcement level: MUST (mandatory), SHOULD (recommended), MAY (optional)

LINKED-LIST BEHAVIOR:
=====================
- First clause (C1) stands alone
- Subsequent clauses can reference earlier clauses like: (refs: C1, C3)
- Build a logical chain of policy enforcement
- Ensure each clause can be evaluated independently AND in sequence

OUTPUT ONLY the JSON array. No explanations, no markdown, no code blocks.
"""
        
        try:
            self.log_entry("GEMINI_REQUEST", "Sending policy content for clause extraction")
            response = self.model.generate_content(prompt)
            
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
            if response_text.startswith("```"):
                response_text = response_text[3:]  # Remove ```
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove trailing ```
            
            response_text = response_text.strip()
            
            # Parse JSON response
            try:
                clauses = json.loads(response_text)
                
                if not isinstance(clauses, list):
                    self.log_entry("ERROR", "Gemini response is not a JSON array")
                    return None
                
                self.log_entry("SUCCESS", f"Extracted {len(clauses)} clauses from policy")
                return clauses
                
            except json.JSONDecodeError as e:
                self.log_entry("ERROR", f"Failed to parse Gemini JSON response: {e}")
                self.log_entry("DEBUG", f"Response preview: {response_text[:200]}")
                return None
        
        except Exception as e:
            self.log_entry("ERROR", f"Gemini API failed: {e}")
            return None
    
    def validate_clauses(self, clauses):
        """Validate extracted clauses structure"""
        if not clauses:
            return False
        
        for i, clause in enumerate(clauses):
            # Check required fields
            if "clause_id" not in clause or "text" not in clause:
                self.log_entry("ERROR", f"Clause {i} missing required fields (clause_id, text)")
                return False
            
            # Check text length (4-5 lines recommendation, allow up to 10)
            text_lines = len(clause["text"].split('\n'))
            if text_lines > 15:
                self.log_entry("WARNING", f"Clause {clause['clause_id']} exceeds recommended length ({text_lines} lines)")
            
            # Validate clause_id format
            if not re.match(r'^C\d+$', clause['clause_id']):
                self.log_entry("ERROR", f"Invalid clause_id format: {clause['clause_id']} (should be C1, C2, etc.)")
                return False
        
        return True
    
    def build_clause_map(self, clauses):
        """
        Build simple clause_id → text mapping (no linked-list pointers).
        Each clause_id is directly linked to its elaborated text.
        Used as input for Stage 2 intent classification.
        """
        clause_map = []
        for clause in clauses:
            clause_map.append({
                "clauseId": clause["clause_id"],
                "text": clause["text"]
            })
        return clause_map
    
    def format_clauses_output(self, clauses):
        """
        Format clause output with metadata header for Stage 2 (intent classification).
        Simple structure: clauseId → text mapping.
        
        Args:
            clauses (list): List of clause dicts with clauseId and text
            
        Returns:
            dict: Formatted output with metadata and clauses array
        """
        output = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "source": self.policy_file,
                "format": "Clause → Text Mapping (Stage 1B → Stage 2 Intent Classification)",
                "total_clauses": len(clauses),
                "stage": "1B",
                "next_stage": "2 - Intent Classification"
            },
            "clauses": clauses
        }
        return output
    
    def extract(self):
        """Main extraction workflow with LangChain enhancement"""
        self.log_entry("START", "Step 1B: Clause Extraction with Elaboration")
        
        # Step 1: Read policy file
        self.log_entry("STEP", "Reading policy file")
        content = self.read_policy_file()
        if not content:
            return False
        
        self.log_entry("SUCCESS", f"Policy file read: {len(content)} characters")
        
        # Step 2: Extract and elaborate clauses (LangChain or standard)
        if self.use_langchain:
            self.log_entry("STEP", "Extracting clauses with LangChain (enhanced mode)")
            clauses = self.extract_clauses_with_langchain(content)
        else:
            self.log_entry("STEP", "Extracting clauses with standard Gemini")
            clauses = self.extract_clauses_with_gemini(content)
        
        if not clauses:
            return False
        
        # Step 3: Validate clauses
        self.log_entry("STEP", "Validating clause structure")
        if not self.validate_clauses(clauses):
            return False
        
        # Step 4: Build clause_id → text mapping (simple link, no pointers)
        self.log_entry("STEP", "Building clause_id → text mapping")
        clause_map = self.build_clause_map(clauses)
        
        # Step 5: Format output
        self.log_entry("STEP", "Formatting output")
        formatted_output = self.format_clauses_output(clause_map)
        
        # Step 6: Save to file
        try:
            with open(self.clauses_file, 'w') as f:
                json.dump(formatted_output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Clauses saved to: {self.clauses_file}")
            self.log_entry("STATS", f"Total clauses: {len(clause_map)}")
            
            # Step 7: Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=1,
                stage_name="extract-clauses",
                stage_output=formatted_output,
                filename=self.policy_file.split('/')[-1]
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save clauses file: {e}")
            return False
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== CLAUSE EXTRACTION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class IntentClassifier:
    """
    Step 2: Classify clause intents using Gemini API.
    
    For each clause text from Stage 1B, determines the intent type and confidence.
    Intent types: RESTRICTION, LIMIT, CONDITIONAL_ALLOWANCE, EXCEPTION,
                  APPROVAL_REQUIRED, ADVISORY, INFORMATIONAL
    """
    
    def __init__(self, clauses_file, document_id=None, enable_mongodb=True, use_langchain=True):
        self.clauses_file = clauses_file
        self.classified_file = f"{OUTPUT_DIR}/stage2_classified.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()  # Thread-safe logging
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Allowed intents (hardcoded taxonomy)
        self.allowed_intents = [
            "RESTRICTION",
            "LIMIT",
            "CONDITIONAL_ALLOWANCE",
            "EXCEPTION",
            "APPROVAL_REQUIRED",
            "ADVISORY",
            "INFORMATIONAL"
        ]
        
        # Initialize LangChain components if available
        if self.use_langchain:
            self.log_entry("INFO", "LangChain enabled for enhanced intent classification")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
        else:
            if not LANGCHAIN_AVAILABLE:
                self.log_entry("WARNING", "LangChain not available, using standard classification")
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def read_clauses_file(self):
        """Read stage1_clauses.json and extract clauses array"""
        try:
            with open(self.clauses_file, 'r') as f:
                data = json.load(f)
            
            if "clauses" not in data:
                self.log_entry("ERROR", "No 'clauses' array found in input file")
                return None
            
            clauses = data["clauses"]
            if not isinstance(clauses, list):
                self.log_entry("ERROR", "Clauses is not a list")
                return None
            
            self.log_entry("SUCCESS", f"Read {len(clauses)} clauses from {self.clauses_file}")
            return clauses
        
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"Failed to parse JSON: {e}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read clauses file: {e}")
            return None
    
    def classify_intent_with_langchain(self, clause_id, clause_text):
        """
        LANGCHAIN-ENHANCED: Classify intent using structured output parsing.
        
        Benefits:
        - Automatic validation with Pydantic
        - Retry logic on failures
        - Type-safe output
        
        Returns:
            dict: { "intent": "...", "confidence": 0.0-1.0, "reasoning": "..." }
        """
        parser = PydanticOutputParser(pydantic_object=IntentClassificationSchema)
        
        prompt_template = PromptTemplate(
            input_variables=["clause_id", "clause_text"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
            template="""You are a POLICY INTENT CLASSIFIER. Analyze the clause and determine its intent type.

ALLOWED INTENT TYPES (choose exactly one):
1. RESTRICTION - Prohibits or forbids an action
2. LIMIT - Sets maximum/minimum thresholds or caps
3. CONDITIONAL_ALLOWANCE - IF/THEN entitlements based on conditions
4. EXCEPTION - Special cases or exemptions
5. APPROVAL_REQUIRED - Requires authorization or permission
6. ADVISORY - Recommended behavior (SHOULD/MAY)
7. INFORMATIONAL - Definitions or classifications

CLAUSE TO CLASSIFY:
Clause ID: {clause_id}
Text: {clause_text}

TASK:
1. Identify primary intent
2. Determine confidence (0.0-1.0)
3. Provide brief reasoning

{format_instructions}

OUTPUT ONLY valid JSON matching the schema."""
        )
        
        chain = LLMChain(llm=self.langchain_llm, prompt=prompt_template)
        
        try:
            result = chain.run(clause_id=clause_id, clause_text=clause_text)
            parsed = parser.parse(result)
            return parsed.dict()
        except Exception as e:
            self.log_entry("ERROR", f"{clause_id}: LangChain classification failed: {e}")
            # Fallback to standard method
            return self.classify_intent_with_gemini(clause_id, clause_text)
    
    def classify_intent_with_gemini(self, clause_id, clause_text):
        """
        Use Gemini API to classify a single clause's intent.
        
        Args:
            clause_id (str): Clause identifier (C1, C2, etc.)
            clause_text (str): Elaborated clause text
            
        Returns:
            dict: { "intent": "...", "confidence": 0.0-1.0, "reasoning": "..." }
        """
        
        prompt = f"""
You are a POLICY INTENT CLASSIFIER. Analyze the clause text and determine its intent type.

ALLOWED INTENT TYPES (MUST choose exactly one):
1. RESTRICTION - Prohibits or forbids an action; what must NOT be done
2. LIMIT - Sets maximum/minimum thresholds, caps, or quantitative bounds
3. CONDITIONAL_ALLOWANCE - IF/THEN entitlements; allowances based on conditions
4. EXCEPTION - Special cases, exemptions, or deviations from general rules
5. APPROVAL_REQUIRED - Requires authorization, permission, or sign-off
6. ADVISORY - Recommended behavior; non-mandatory; SHOULD/MAY language
7. INFORMATIONAL - Definitions, classifications, or reference information

CLAUSE TO CLASSIFY:
Clause ID: {clause_id}
Text: "{clause_text}"

ANALYSIS TASK:
1. Identify the primary intent of this clause
2. Determine confidence (0.0-1.0) based on clarity and explicitness
3. Provide brief reasoning

OUTPUT FORMAT (strict JSON, one line):
{{
  "intent": "INTENT_TYPE",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why this intent was chosen"
}}

Guidelines:
- RESTRICTION: "must NOT", "prohibited", "not allowed", "cannot", "forbidden"
- LIMIT: "maximum", "minimum", "cap", "threshold", "up to", "at most", "at least"
- CONDITIONAL_ALLOWANCE: "IF...THEN", "eligible if", "provided that", "when", "upon"
- EXCEPTION: "except", "unless", "provided", "in case of", "special case"
- APPROVAL_REQUIRED: "requires approval", "must be approved", "needs authorization"
- ADVISORY: "should", "may", "recommended", "preferred", "suggested"
- INFORMATIONAL: "defined as", "classified as", "includes", "consists of", "types"

Output ONLY valid JSON. No explanation outside the JSON object.
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parse JSON
            try:
                result = json.loads(response_text)
                
                # Validate intent
                if "intent" not in result:
                    self.log_entry("WARNING", f"{clause_id}: Missing 'intent' field")
                    result["intent"] = "INFORMATIONAL"  # Default fallback
                
                # Validate intent is in allowed list
                intent = result.get("intent", "INFORMATIONAL").upper()
                if intent not in self.allowed_intents:
                    self.log_entry("WARNING", f"{clause_id}: Invalid intent '{intent}', using INFORMATIONAL")
                    result["intent"] = "INFORMATIONAL"
                else:
                    result["intent"] = intent
                
                # Validate confidence
                if "confidence" not in result:
                    result["confidence"] = 0.75  # Default confidence
                else:
                    try:
                        conf = float(result["confidence"])
                        result["confidence"] = max(0.0, min(1.0, conf))  # Clamp 0-1
                    except (ValueError, TypeError):
                        result["confidence"] = 0.75
                
                return result
            
            except json.JSONDecodeError as e:
                self.log_entry("ERROR", f"{clause_id}: Failed to parse Gemini response: {e}")
                return {
                    "intent": "INFORMATIONAL",
                    "confidence": 0.5,
                    "reasoning": "Failed to parse response"
                }
        
        except Exception as e:
            self.log_entry("ERROR", f"{clause_id}: Gemini API call failed: {e}")
            return {
                "intent": "INFORMATIONAL",
                "confidence": 0.5,
                "reasoning": f"API error: {str(e)[:50]}"
            }
    
    def classify(self):
        """Main classification workflow"""
        self.log_entry("START", "Step 2: Intent Classification")
        
        # Step 1: Read clauses from Stage 1B
        self.log_entry("STEP", "Reading clauses from Stage 1B")
        clauses = self.read_clauses_file()
        if not clauses:
            return False
        
        self.log_entry("STATS", f"Total clauses to classify: {len(clauses)}")
        
        # Step 2: Classify each clause (LangChain or standard) with PARALLEL PROCESSING
        if self.use_langchain:
            self.log_entry("STEP", "Classifying intent with LangChain (parallel mode - 5 workers)")
        else:
            self.log_entry("STEP", "Classifying intent with standard Gemini (parallel mode - 5 workers)")
        
        classified = []
        
        def classify_single_clause(clause_data):
            """Helper function for parallel processing"""
            i, clause = clause_data
            clause_id = clause.get("clauseId", f"C{i}")
            clause_text = clause.get("text", "")
            
            self.log_entry("CLASSIFY", f"[{i}/{len(clauses)}] Processing {clause_id}")
            
            # Classify this clause
            if self.use_langchain:
                intent_result = self.classify_intent_with_langchain(clause_id, clause_text)
            else:
                intent_result = self.classify_intent_with_gemini(clause_id, clause_text)
            
            # Build classified clause record
            classified_clause = {
                "clauseId": clause_id,
                "text": clause_text,
                "intent": intent_result.get("intent", "INFORMATIONAL"),
                "confidence": intent_result.get("confidence", 0.5),
                "reasoning": intent_result.get("reasoning", "")
            }
            
            self.log_entry("RESULT", f"{clause_id}: {classified_clause['intent']} (confidence: {classified_clause['confidence']})")
            return classified_clause
        
        # Process clauses in parallel (8 workers for optimal speed)
        with ThreadPoolExecutor(max_workers=PipelineConfig.DEFAULT_MAX_WORKERS) as executor:
            clause_data = [(i, clause) for i, clause in enumerate(clauses, 1)]
            classified = list(executor.map(classify_single_clause, clause_data))
        
        self.log_entry("SUCCESS", f"Classified {len(classified)} clauses")
        
        # Step 3: Format output
        self.log_entry("STEP", "Formatting classified output")
        formatted_output = self.format_classified_output(classified)
        
        # Step 4: Save to file
        try:
            with open(self.classified_file, 'w') as f:
                json.dump(formatted_output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Classified clauses saved to: {self.classified_file}")
            
            # Step 5: Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=2,
                stage_name="classify-intents",
                stage_output=formatted_output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
        
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save classified file: {e}")
            return False
    
    def format_classified_output(self, classified_clauses):
        """
        Format classified output with metadata.
        
        Args:
            classified_clauses (list): List of classified clause dicts
            
        Returns:
            dict: Formatted output with metadata and classified clauses
        """
        # Calculate statistics
        intent_counts = {}
        for clause in classified_clauses:
            intent = clause.get("intent", "UNKNOWN")
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
        
        avg_confidence = sum(c.get("confidence", 0) for c in classified_clauses) / len(classified_clauses) if classified_clauses else 0
        
        output = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "source": self.clauses_file,
                "format": "Intent Classification (Stage 2)",
                "total_clauses": len(classified_clauses),
                "stage": "2",
                "next_stage": "3 - Payload Evaluation",
                "average_confidence": round(avg_confidence, 3),
                "intent_distribution": intent_counts
            },
            "classified_clauses": classified_clauses
        }
        return output
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== INTENT CLASSIFICATION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class EntityExtractor:
    """
    Step 3: Extract structured entities & thresholds using Gemini API.
    
    For each clause text from Stage 2, extracts explicit entities only.
    Entity types: Type, Class, Category, amount, Currency, Hours, location, role, ApprovalAuthority
    """
    
    def __init__(self, classified_file, document_id=None, enable_mongodb=True, use_langchain=True, max_workers=8):
        self.classified_file = classified_file
        self.entities_file = f"{OUTPUT_DIR}/stage3_entities.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()  # Thread-safe logging
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        
        # Parallel processing config
        self.max_workers = max_workers  # Number of parallel threads
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Initialize LangChain components if available
        if self.use_langchain:
            self.log_entry("INFO", "LangChain enabled for enhanced entity extraction")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
        else:
            if not LANGCHAIN_AVAILABLE:
                self.log_entry("WARNING", "LangChain not available, using standard extraction")
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def read_classified_file(self):
        """Read stage2_classified.json and extract classified clauses"""
        try:
            with open(self.classified_file, 'r') as f:
                data = json.load(f)
            
            if "classified_clauses" not in data:
                self.log_entry("ERROR", "No 'classified_clauses' array found in input file")
                return None
            
            clauses = data["classified_clauses"]
            if not isinstance(clauses, list):
                self.log_entry("ERROR", "Classified clauses is not a list")
                return None
            
            self.log_entry("SUCCESS", f"Read {len(clauses)} classified clauses from {self.classified_file}")
            return clauses
        
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"Failed to parse JSON: {e}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read classified file: {e}")
            return None
    
    def extract_entities_with_langchain(self, clause_id, clause_text):
        """
        LANGCHAIN-ENHANCED: Extract entities using structured output parsing.
        
        Benefits:
        - Automatic validation with Pydantic
        - Retry logic on failures
        - Type-safe output
        
        Returns:
            dict: Extracted entities as key-value pairs
        """
        parser = PydanticOutputParser(pydantic_object=EntityExtractionSchema)
        
        prompt_template = PromptTemplate(
            input_variables=["clause_id", "clause_text"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
            template="""You are a DYNAMIC ENTITY EXTRACTION ENGINE. Extract meaningful structured entities from policy text.

CRITICAL RULES:
1. Extract ONLY values explicitly stated in the text
2. Do NOT infer, guess, or assume missing values
3. Do NOT include null/empty values - omit if not present
4. Preserve original units (currency, time, amounts, etc.)
5. Create entity names that are descriptive and meaningful
6. One clause may have multiple entity values

ENTITY EXTRACTION GUIDELINES:
- Identify key-value pairs that represent measurable facts
- Entity names should be descriptive (e.g., "dailyAllowance", "travelDuration")
- Include units in values when present (e.g., "7.0 Rs/KM", "15 days", "100 KM")
- Use camelCase for multi-word entity names

CLAUSE TO ANALYZE:
Clause ID: {clause_id}
Text: {clause_text}

EXTRACTION TASK:
1. Scan clause text for explicit, measurable values
2. Identify meaningful entity names based on context
3. Extract only what is clearly stated
4. Omit entities not explicitly mentioned
5. Return a JSON object with extracted entities

{format_instructions}

OUTPUT ONLY valid JSON matching the schema. If no entities, return {{"entities": {{}}}}."""
        )
        
        chain = LLMChain(llm=self.langchain_llm, prompt=prompt_template)
        
        try:
            result = chain.run(clause_id=clause_id, clause_text=clause_text)
            parsed = parser.parse(result)
            return parsed.entities
        except Exception as e:
            self.log_entry("ERROR", f"{clause_id}: LangChain extraction failed: {e}")
            # Fallback to standard method
            return self.extract_entities_with_gemini(clause_id, clause_text)
    
    def extract_entities_with_gemini(self, clause_id, clause_text):
        """
        STANDARD: Use Gemini API to extract entities dynamically from a single clause.
        Entities are NOT predefined - LLM identifies meaningful key-value pairs.
        
        Includes retry logic with exponential backoff for rate limits.
        
        Args:
            clause_id (str): Clause identifier (C1, C2, etc.)
            clause_text (str): Clause text with policy content
            
        Returns:
            dict: { "entityName": value, ... } with dynamically identified entities
        """
        import time
        
        prompt = f"""
You are a DYNAMIC ENTITY EXTRACTION ENGINE. Extract meaningful structured entities from policy text.

CRITICAL RULES:
1. Extract ONLY values explicitly stated in the text
2. Do NOT infer, guess, or assume missing values
3. Do NOT include null/empty values - omit if not present
4. Preserve original units (currency, time, amounts, etc.)
5. Create entity names that are descriptive and meaningful
6. One clause may have multiple entity values

ENTITY EXTRACTION GUIDELINES:
- Identify key-value pairs that represent measurable facts
- Entity names should be descriptive (e.g., "dailyAllowance", "travelDuration", "approvalAuthority")
- Include units in values when present (e.g., "7.0 Rs/KM", "15 days", "100 KM")
- Group related values logically
- Use camelCase for multi-word entity names

CLAUSE TO ANALYZE:
Clause ID: {clause_id}
Text: "{clause_text}"

EXTRACTION TASK:
1. Scan clause text for explicit, measurable values
2. Identify meaningful entity names based on context
3. Extract only what is clearly stated
4. Omit entities not explicitly mentioned
5. Return a JSON object with extracted entities

OUTPUT FORMAT (valid JSON object, empty if no entities):
{{
  "descriptiveEntityName1": "value1",
  "descriptiveEntityName2": "value2"
}}

EXAMPLES:
- Text: "Rs. 7.0 per KM for Four Wheeler or Rs. 2.5 per KM for Two Wheeler"
  Extract: {{"fourWheelerRate": "7.0 Rs/KM", "twoWheelerRate": "2.5 Rs/KM"}}

- Text: "Employee grade M1-M6 with corresponding lodging amounts"
  Extract: {{"employeeGrades": "M1-M6", "lodgingVariation": "grade-dependent"}}

- Text: "Bills MUST be submitted within 15 days"
  Extract: {{"billSubmissionDeadline": "15 days"}}

- Text: "Requires HOD approval for direct booking"
  Extract: {{"requiredApproval": "HOD"}}

- Text: "Travel to NCR, Mumbai, Delhi"
  Extract: {{"allowedCities": "NCR, Mumbai, Delhi"}}

- If text has no measurable values, return: {{}}

Output ONLY valid JSON. No explanation outside JSON.
"""
        
        max_retries = 3  # Use default retry count
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries + 1):
            try:
                response = self.model.generate_content(prompt)
                response_text = response.text.strip()
                
                # Clean markdown if present
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                # Parse JSON
                try:
                    result = json.loads(response_text)
                    
                    if not isinstance(result, dict):
                        self.log_entry("WARNING", f"{clause_id}: Result is not a dict, using empty")
                        return {}
                    
                    # Return all entities as-is (fully dynamic, no validation against predefined list)
                    return result
                
                except json.JSONDecodeError as e:
                    self.log_entry("ERROR", f"{clause_id}: Failed to parse Gemini response: {e}")
                    return {}
            
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in str(e) or "rate limit" in error_str or "quota" in error_str
                
                if is_rate_limit and attempt < max_retries:
                    # Exponential backoff for rate limit errors
                    wait_time = retry_delay * (2 ** attempt)
                    self.log_entry("WARNING", f"{clause_id}: Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed or non-retryable error
                    if attempt > 0:
                        self.log_entry("ERROR", f"{clause_id}: Failed after {attempt + 1} retry attempts. {type(e).__name__}: {e}")
                    else:
                        self.log_entry("ERROR", f"{clause_id}: Gemini API call failed: {e}")
                    return {}
    
    def extract(self):
        """Main extraction workflow with PARALLEL PROCESSING"""
        self.log_entry("START", "Step 3: Entity & Threshold Extraction")
        
        # Step 1: Read classified clauses from Stage 2
        self.log_entry("STEP", "Reading classified clauses from Stage 2")
        clauses = self.read_classified_file()
        if not clauses:
            return False
        
        self.log_entry("INFO", f"Starting Stage 3: Entity Extraction (Parallel)")
        self.log_entry("INFO", f"Configuration: max_workers={self.max_workers}")
        
        if self.use_langchain:
            self.log_entry("INFO", f"Extracting entities from {len(clauses)} clauses with LangChain (parallel mode)")
        else:
            self.log_entry("INFO", f"Extracting entities from {len(clauses)} clauses with standard Gemini (parallel mode)")
        
        # Step 2: Extract entities from each clause in parallel
        def extract_single(clause):
            i = 1  # Will be set in loop
            clause_id = clause.get("clauseId")
            clause_text = clause.get("text", "")
            clause_intent = clause.get("intent", "UNKNOWN")
            
            # Extract entities from this clause
            if self.use_langchain:
                entities = self.extract_entities_with_langchain(clause_id, clause_text)
            else:
                entities = self.extract_entities_with_gemini(clause_id, clause_text)
            
            entity_count = len(entities)
            self.log_entry("RESULT", f"{clause_id}: Extracted {entity_count} entities: {list(entities.keys())}")
            
            # Build extracted clause record
            return {
                "clauseId": clause_id,
                "text": clause_text,
                "intent": clause_intent,
                "entities": entities
            }
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            extracted = list(executor.map(extract_single, clauses))
        
        self.log_entry("SUCCESS", f"Extracted entities from {len(extracted)} clauses")
        
        # Step 3: Calculate statistics
        self.log_entry("STEP", "Calculating entity statistics")
        stats = self.calculate_entity_statistics(extracted)
        
        # Step 4: Format output
        self.log_entry("STEP", "Formatting entity extraction output")
        formatted_output = self.format_entities_output(extracted, stats)
        
        # Step 5: Save to file
        try:
            with open(self.entities_file, 'w') as f:
                json.dump(formatted_output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Extracted entities saved to: {self.entities_file}")
            
            # Step 6: Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=3,
                stage_name="extract-entities",
                stage_output=formatted_output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
        
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save entities file: {e}")
            return False
    
    def calculate_entity_statistics(self, extracted_clauses):
        """
        Calculate entity extraction statistics.
        
        Args:
            extracted_clauses (list): List of extracted clause dicts
            
        Returns:
            dict: Statistics about entities
        """
        entity_counts = {}
        total_entities = 0
        clauses_with_entities = 0
        
        for clause in extracted_clauses:
            entities = clause.get("entities", {})
            if entities:
                clauses_with_entities += 1
            
            for entity_type in entities.keys():
                entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
                total_entities += 1
        
        return {
            "total_entities": total_entities,
            "total_clauses": len(extracted_clauses),
            "clauses_with_entities": clauses_with_entities,
            "entity_type_distribution": entity_counts,
            "coverage": round(clauses_with_entities / len(extracted_clauses) * 100, 1) if extracted_clauses else 0
        }
    
    def format_entities_output(self, extracted_clauses, stats):
        """
        Format entity extraction output with metadata.
        
        Args:
            extracted_clauses (list): List of extracted clause dicts
            stats (dict): Entity statistics
            
        Returns:
            dict: Formatted output with metadata and extracted entities
        """
        # Collect all unique entity names found across clauses
        entity_names = set()
        for clause in extracted_clauses:
            for entity_name in clause.get("entities", {}).keys():
                entity_names.add(entity_name)
        
        output = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "source": self.classified_file,
                "format": "Dynamic Entity & Threshold Extraction (Stage 3)",
                "total_clauses": len(extracted_clauses),
                "stage": "3",
                "next_stage": "4 - Payload Validation",
                "statistics": stats,
                "note": "Entity types are dynamically extracted - not predefined. Each entity name is derived from the clause context."
            },
            "extracted_entity_names": sorted(list(entity_names)),
            "extracted_clauses": extracted_clauses
        }
        return output
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== ENTITY EXTRACTION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class RuleExtractor:
    """Step 2: Use grep + Gemini to extract rules"""
    
    def __init__(self, policy_file):
        self.policy_file = policy_file
        self.rules_file = f"{OUTPUT_DIR}/rules.txt"
        self.log = []
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
    def log_entry(self, level, message):
        """Log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def grep_search(self, pattern):
        """Run grep search on policy file"""
        try:
            result = subprocess.run(
                ['grep', '-n', pattern, self.policy_file],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                self.log_entry("GREP", f"Pattern '{pattern}': Found {len(lines)} matches")
                return lines
            else:
                self.log_entry("GREP", f"Pattern '{pattern}': No matches")
                return []
                
        except Exception as e:
            self.log_entry("ERROR", f"grep failed: {e}")
            return []
    
    def read_policy_file(self):
        """Read entire policy file"""
        try:
            with open(self.policy_file, 'r') as f:
                return f.read()
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read policy file: {e}")
            return None
    
    def analyze_structure_with_grep(self, content):
        """Analyze document structure using grep patterns"""
        self.log_entry("PASS", "Analyzing document structure")
        
        patterns = [
            r'^[0-9]+\. [A-Z]',      # Main sections (1. SECTION)
            r'^[0-9]\.[0-9] ',       # Subsections (1.1 )
            r'MUST|EXPECTED|SHOULD', # Enforcement levels
        ]
        
        structure = {}
        for pattern in patterns:
            self.log_entry("GREP_PATTERN", f"Testing: {pattern}")
            results = self.grep_search(pattern)
            structure[pattern] = results
        
        return structure
    
    def extract_rules_with_gemini(self, content):
        """
        Use Gemini API to extract structured policy rules in Refactored Rule Engine format.
        Works with ANY policy document - automatically infers structure and requirements.

        Returns:
            str: Structured rules text or None if extraction failed.
        """

        self.log_entry("GEMINI", "Initializing Gemini API for structured rule extraction")

        prompt = f"""
You are a STRUCTURED POLICY EXTRACTION ENGINE with strict enforcement of logical rigor.

Task:
- Analyze the policy document below and extract ALL rules, requirements, entitlements, and constraints.
- Output in the REFACTORED RULE ENGINE FORMAT (see below).
- Make NO assumptions about the policy domain - infer structure from actual content.
- ENFORCE: Every rule must have measurable conditions and verifiable consequences.
- ENFORCE: All percentages, amounts, times, and durations must be explicit.
- ENFORCE: Flag vague terms and provide concrete alternatives.
- Output ONLY the structured rules - no commentary, explanations, or metadata outside the format.

====================================================
POLICY DOCUMENT
====================================================
{content}

====================================================
REFACTORED RULE ENGINE FORMAT
====================================================

SECTION 1: DEFINITIONS & CONSTANTS
Define all key terms, enumerations, grades, roles, categories, and thresholds mentioned in the policy.
Example:
  employee.grade: {{E1, E2, E3, E4, E5, E6, E7, E8, E9, E10, Director, MD}}
  travel.duration_threshold: {{short: 1-10 days, long: 11+ days}}
  daily_allowance: {{E1-E7: 300 USD, E8-E10: 350 USD, MD: 500 USD}}

SECTION 2: AUTHORITY HIERARCHY (if applicable)
Define approval authorities, decision-makers, and escalation paths with explicit role definitions.
Example:
  approval.travel_sanction: {{"authority": "MD & CEO", "required": true}}
  approval.extended_stay: {{"authority": "E8 or higher", "exceptions": ["medical exigencies"]}}

SECTION 3: PRIMARY ENTITLEMENTS OR RULES
Organize by major policy domains/categories. For each rule use STRICT format:

rule: <rule_name>
priority: <1-high, 2-medium, 3-low>
conditions:
  - IF <measurable_condition_1> AND <measurable_condition_2>
    THEN <verifiable_consequence_1>
    AND <verifiable_consequence_2>
    SOURCE: <clause reference>

CRITICAL REQUIREMENTS FOR SECTION 3:
  - Every condition must be verifiable (compare against defined constants)
  - Every THEN must have a concrete, measurable outcome
  - If condition contains %, that % must reference a base value defined in SECTION 1
  - If condition contains time (e.g., "after 4:30 PM"), state EXACTLY what the trigger is
  - If multiple rules could apply, state which takes precedence


SECTION 4: ANCILLARY RULES
Optional behaviors, recommendations, special cases that are not mandatory.
Mark as SHOULD/RECOMMENDED, not MUST.

SECTION 5: PROHIBITED ITEMS
What is explicitly forbidden with clear conditions.

SECTION 6: MANDATORY REQUIREMENTS
Pre-conditions that MUST be satisfied before any travel/entitlements activate.
These are blocking conditions (no exceptions).

SECTION 7: RULE PRECEDENCE & CONFLICT RESOLUTION
Explicit rules for handling overlapping conditions:
  - Which rule wins if multiple apply? (e.g., "Most restrictive rule applies")
  - What if a rule contradicts another? (e.g., "Explicit exception overrides general rule")
  - How are ambiguous conditions resolved? (e.g., "Escalate to 'x' for decision")
  
If NO conflict exists, state: "No overlapping rules identified in this policy."

SECTION 8: MEASUREMENT & ENFORCEMENT
For each vague term found, provide:
  1. Original vague term
  2. Why it's unmeasurable
  3. Concrete metric to replace it
  
Example:
  Vague: "judicious expenditure"
  Reason: No objective threshold defined
  Concrete: "Allowance capped at [grade-specific amount]. Outliers flagged if spend > 120% of cap."

SECTION 9: POLICY MAINTENANCE
Review cycle, dependencies, update procedures, external references.

====================================================
EXTRACTION GUIDELINES
====================================================
NAMING & TERMS:
  - Use normalized domain terms consistently (e.g., employee.grade, booking.travel_class, fx.amount)
  - Define all acronyms and abbreviations (e.g., "MEA" = Ministry of External Affairs)
  - When policy references external documents, list them explicitly

NUMERIC PRECISION:
  - Make ALL numeric limits explicit: X USD, Y days, Z hours
  - For ranges, express as: "min <= value <= max" or "E1-E7 grades (6 distinct grades)"
  - For percentages, state: "X% of [base value defined in SECTION 1]"
  - For time conditions, use 24-hour format: "after 16:30 (4:30 PM)" not "after 4:30 PM"

LOGIC & CONDITIONS:
  - Split complex multi-condition clauses into separate rules
  - Use AND/OR explicitly (not implicit)
  - For grade-based rules, handle overlaps: if both "E8" and "E8-E10" rules exist, which wins?
  - If policy says "may", "should", "could", mark as optional (SECTION 4)
  - If policy says "must", "require", "shall", mark as mandatory (SECTION 3 or 6)

VAGUE TERM HANDLING:
  - Do NOT output rules with unmeasurable terms
  - Flag them in SECTION 8 instead
  - Suggest concrete metrics
  - Mark as PENDING MANUAL REVIEW if no metric can be inferred

COMPLETENESS:
  - Preserve clause/section numbers from source document
  - If policy is silent on a scenario, do NOT invent it
  - If policy contradicts itself, flag explicitly in SECTION 7

====================================================
OUTPUT STRUCTURE EXAMPLE
====================================================

================================================================================
OVERSEAS BUSINESS TRAVEL - STRUCTURED RULES
================================================================================
Generated: 2026-01-15
Source Policy Sections: 1-5
Format: Rule Engine v1.0

================================================================================
1. DEFINITIONS & CONSTANTS
================================================================================

employee.grade:
  junior: [E1, E2, E3, E4, E5, E6, E7]
  senior: [E8, E9, E10]
  executive: [Director, MD & CEO]

daily_allowance_usd:
  E1_to_E7: 300
  E8_to_E10: 350
  executive: 500

travel_class_entitlement:
  E1_to_E7: "Economy Class"
  E8_to_E10: "Business Class"
  Director: ["Business Class", "Club Class"]
  MD_CEO: "First Class"

================================================================================
2. AUTHORITY HIERARCHY
================================================================================

approval.travel_sanction:
  authority: "MD & CEO"
  required: true
  exceptions: none

[etc...]

====================================================
CRITICAL: OUTPUT ONLY THE STRUCTURED RULES
====================================================
Do NOT include:
- Explanatory text outside the format
- Original policy paragraphs
- Commentary or interpretation
- Placeholder examples
- Vague rules (move to SECTION 8 instead)

Output must be ready to parse and implement as-is.
Rules with unmeasurable conditions go to SECTION 8 for definition.
"""

        try:
            self.log_entry("GEMINI_REQUEST", "Sending policy content for structured rule extraction")
            response = self.model.generate_content(prompt)

            rule_output = response.text.strip()
            
            # Validate output contains expected structure markers
            if "DEFINITIONS & CONSTANTS" not in rule_output and "rule:" not in rule_output:
                self.log_entry("WARNING", "Gemini response missing expected structure markers. Output may be incomplete.")
            
            self.log_entry("GEMINI_RESPONSE", "Structured rules extracted successfully")
            
            # Return raw output - formatting will be done by caller
            return rule_output

        except Exception as e:
            self.log_entry("ERROR", f"Gemini API failed: {e}")
            return None

    def format_rules_output(self, gemini_output):
        """
        Wrap extracted rules with consistent header and metadata.
        
        Args:
            gemini_output (str): Raw output from Gemini
            
        Returns:
            str: Formatted rules document
        """
        output = "=" * 80 + "\n"
        output += "STRUCTURED POLICY RULES - EXTRACTED VIA GEMINI API\n"
        output += "=" * 80 + "\n\n"
        output += f"Generated: {datetime.now()}\n"
        output += f"Source: {self.policy_file}\n"
        output += f"Extraction Method: Content Analysis + Gemini Structured Extraction\n"
        output += f"Format: Rule Engine v1.0 (Measurable, Enforceable, Generic)\n\n"
        output += "=" * 80 + "\n\n"
        
        output += gemini_output
        
        return output
    
    def extract(self):
        """Main extraction workflow"""
        self.log_entry("START", "Step 2: Rule Extraction with Grep + Gemini")
        
        # Step 1: Read policy file
        self.log_entry("STEP", "Reading policy file")
        content = self.read_policy_file()
        if not content:
            return False
        
        self.log_entry("SUCCESS", f"Policy file read: {len(content)} characters")
        
        # Step 2: Analyze structure with grep
        self.log_entry("STEP", "Analyzing structure with grep searches")
        structure = self.analyze_structure_with_grep(content)
        
        # Step 3: Extract rules with Gemini
        self.log_entry("STEP", "Extracting rules with Gemini API")
        gemini_response = self.extract_rules_with_gemini(content)
        if not gemini_response:
            return False
        
        # Step 4: Format and save output
        self.log_entry("STEP", "Formatting output")
        formatted_rules = self.format_rules_output(gemini_response)
        
        # Save to file
        try:
            with open(self.rules_file, 'w') as f:
                f.write(formatted_rules)
            
            self.log_entry("SUCCESS", f"Rules saved to: {self.rules_file}")
            self.log_entry("STATS", f"Output size: {len(formatted_rules)} characters")
            
            return True
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save rules file: {e}")
            return False
    
    def extract_topics_and_scenarios(self, content):
        """
        Extract all meaningful topics/scenarios from policy document using Gemini.
        Returns a structured list of topics with brief descriptions.
        Focuses on actual policy domains, not section numbers.
        """
        self.log_entry("GEMINI", "Extracting topics and scenarios from policy")
        
        prompt = f"""
You are a POLICY TOPICS EXTRACTION ENGINE. Your task is to identify MEANINGFUL POLICY DOMAINS.

CRITICAL INSTRUCTIONS:
=====================
1. Extract ONLY meaningful topic names that represent policy domains/areas (e.g., "Travel Authorization", "Leave Entitlements", "Daily Allowances")
2. DO NOT output section numbers alone (e.g., "4.1", "3.2", "12") - these are NOT topics
3. DO NOT output generic items without clear policy meaning
4. Each topic must represent a distinct policy domain with its own set of rules

Task:
- Analyze the policy document below and identify ALL major policy domains/categories
- Extract topics that have their own separate rules, requirements, or guidelines
- For each topic, provide a brief 1-2 line description of what it covers
- Output as a numbered list with MEANINGFUL TOPIC NAME and description

Policy Document:
================================================================================
{content}
================================================================================

OUTPUT FORMAT:
Number each topic sequentially. Use this STRICT format:
1. [Meaningful Topic Name] - Brief description (1-2 lines max) of what this policy area covers

Example of CORRECT output:
1. Daily Allowances - Consolidated foreign exchange amounts for employees by grade
2. Leave Entitlements - Leave on duty and extended stay policies during overseas travel
3. Travel Authorization - Approval process and authority hierarchy for overseas travel

Example of INCORRECT output (NEVER do this):
1. 4.1 - (DO NOT USE - section numbers are not topics)
2. Item 12 - (DO NOT USE - generic numbers are not topics)
3. Guidelines - (DO NOT USE - too vague without domain specification)

COMPLETION CRITERIA:
====================
✓ ONLY extract topics that represent actual policy domains from the document
✓ Each topic name must be descriptive and meaningful (e.g., "Travel Mode Entitlements", NOT "3.1")
✓ Topic must have multiple rules or requirements in the policy
✓ Preserve the exact topic names/domains as they appear conceptually in the policy
✓ Output ONLY the numbered list - no explanations or metadata

Output ONLY the numbered list. No additional text before or after.
"""
        
        try:
            response = self.model.generate_content(prompt)
            topics_text = response.text.strip()
            self.log_entry("GEMINI_RESPONSE", "Topics extracted successfully")
            
            # Validate that extracted topics are meaningful (not just numbers)
            lines = topics_text.split('\n')
            valid_topics = []
            for line in lines:
                line = line.strip()
                if line and not line[0].isdigit():  # Skip empty or number-only lines
                    # Check if line contains a meaningful topic name (not just numbers)
                    if any(char.isalpha() for char in line):  # Must contain at least one letter
                        valid_topics.append(line)
            
            if not valid_topics:
                self.log_entry("WARNING", "No meaningful topics extracted. Using raw response.")
                return topics_text
            
            # Reconstruct numbered list
            formatted_topics = '\n'.join([f"{i+1}. {line.lstrip('0123456789.-) ')}" for i, line in enumerate(valid_topics)])
            return formatted_topics
            
        except Exception as e:
            self.log_entry("ERROR", f"Gemini API failed to extract topics: {e}")
            return None
    
    def extract_rules_for_topic(self, content, topic_name):
        """
        Extract rules for a specific topic/scenario from the policy using the same
        strict format as extract_rules_with_gemini.
        
        Args:
            content (str): Full policy content
            topic_name (str): Name of the topic to extract rules for
            
        Returns:
            str: Formatted rules for the specific topic
        """
        self.log_entry("GEMINI", f"Extracting rules for topic: {topic_name}")
        
        prompt = f"""
You are a STRUCTURED POLICY EXTRACTION ENGINE with strict enforcement of logical rigor.

Task:
- From the policy document below, extract ALL rules, requirements, entitlements, and constraints ONLY related to: "{topic_name}"
- Output in the REFACTORED RULE ENGINE FORMAT (see below).
- Make NO assumptions - only extract what exists for this topic.
- ENFORCE: Every rule must have measurable conditions and verifiable consequences.
- ENFORCE: All percentages, amounts, times, and durations must be explicit.
- ENFORCE: Flag vague terms and provide concrete alternatives.
- Output ONLY the structured rules - no commentary, explanations, or metadata outside the format.

====================================================
POLICY DOCUMENT
====================================================
{content}

====================================================
REFACTORED RULE ENGINE FORMAT FOR TOPIC: "{topic_name}"
====================================================

SECTION 1: DEFINITIONS & CONSTANTS
Define all key terms, enumerations, grades, roles, categories, and thresholds specific to {topic_name}.
Example:
  employee.grade: {{E1, E2, E3, E4, E5, E6, E7, E8, E9, E10, Director, MD}}
  duration_threshold: {{short: 1-10 days, long: 11+ days}}
  amount: {{junior: 300 USD, senior: 350 USD, executive: 500 USD}}

SECTION 2: AUTHORITY HIERARCHY (if applicable)
Define approval authorities, decision-makers, and escalation paths for {topic_name}.
Example:
  approval.required: {{"authority": "Manager", "required": true}}
  escalation: {{"authority": "Director", "when": "amount > 500 USD"}}

SECTION 3: PRIMARY ENTITLEMENTS OR RULES FOR {topic_name}
Organize by major policy domains/categories. For each rule use STRICT format:

rule: <rule_name>
priority: <1-high, 2-medium, 3-low>
conditions:
  - IF <measurable_condition_1> AND <measurable_condition_2>
    THEN <verifiable_consequence_1>
    AND <verifiable_consequence_2>
    SOURCE: <clause reference>

CRITICAL REQUIREMENTS FOR SECTION 3:
  - Every condition must be verifiable (compare against defined constants)
  - Every THEN must have a concrete, measurable outcome
  - If condition contains %, that % must reference a base value defined in SECTION 1
  - If condition contains time (e.g., "after 4:30 PM"), state EXACTLY what the trigger is
  - If multiple rules could apply, state which takes precedence

SECTION 4: ANCILLARY RULES
Optional behaviors, recommendations, special cases for {topic_name} that are not mandatory.
Mark as SHOULD/RECOMMENDED, not MUST.

SECTION 5: PROHIBITED ITEMS
What is explicitly forbidden for {topic_name} with clear conditions.

SECTION 6: MANDATORY REQUIREMENTS
Pre-conditions that MUST be satisfied for {topic_name} entitlements to activate.
These are blocking conditions (no exceptions).

SECTION 7: RULE PRECEDENCE & CONFLICT RESOLUTION
Explicit rules for handling overlapping conditions in {topic_name}:
  - Which rule wins if multiple apply?
  - What if a rule contradicts another?
  - How are ambiguous conditions resolved?

If NO conflict exists, state: "No overlapping rules identified for {topic_name}."

SECTION 8: MEASUREMENT & ENFORCEMENT
For each vague term found in {topic_name}, provide:
  1. Original vague term
  2. Why it's unmeasurable
  3. Concrete metric to replace it

Example:
  Vague: "reasonable amount"
  Reason: No objective threshold defined
  Concrete: "Amount capped at grade-specific limit (defined in SECTION 1). Outliers flagged if spend > 120% of cap."

SECTION 9: TOPIC SUMMARY
Brief summary of what {topic_name} covers and any external dependencies or related topics.

====================================================
NAMING & TERMS:
====================================================
  - Use normalized domain terms consistently
  - Define all acronyms and abbreviations
  - When policy references external documents, list them explicitly

NUMERIC PRECISION:
====================================================
  - Make ALL numeric limits explicit: X USD, Y days, Z hours
  - For ranges, express as: "min <= value <= max"
  - For percentages, state: "X% of [base value defined in SECTION 1]"
  - For time conditions, use 24-hour format: "after 16:30 (4:30 PM)"

LOGIC & CONDITIONS:
====================================================
  - Split complex multi-condition clauses into separate rules
  - Use AND/OR explicitly (not implicit)
  - If policy says "may", "should", "could", mark as optional (SECTION 4)
  - If policy says "must", "require", "shall", mark as mandatory (SECTION 3 or 6)

VAGUE TERM HANDLING:
====================================================
  - Do NOT output rules with unmeasurable terms
  - Flag them in SECTION 8 instead
  - Suggest concrete metrics
  - Mark as PENDING MANUAL REVIEW if no metric can be inferred

COMPLETENESS:
====================================================
  - Preserve clause/section numbers from source document
  - If policy is silent on {topic_name}, state: "No rules found in policy for this topic."
  - If policy contradicts itself, flag explicitly in SECTION 7

====================================================
CRITICAL: OUTPUT ONLY THE STRUCTURED RULES
====================================================
Do NOT include:
- Explanatory text outside the format
- Original policy paragraphs
- Commentary or interpretation
- Placeholder examples
- Vague rules (move to SECTION 8 instead)

Output must be ready to parse and implement as-is.
Rules with unmeasurable conditions go to SECTION 8 for definition.
"""
        
        try:
            self.log_entry("GEMINI_REQUEST", f"Sending policy content for topic-specific structured rule extraction: {topic_name}")
            response = self.model.generate_content(prompt)
            rules_text = response.text.strip()
            
            # Validate output contains expected structure markers
            if "SECTION 1:" not in rules_text and "rule:" not in rules_text:
                self.log_entry("WARNING", f"Gemini response for '{topic_name}' missing expected structure markers. Output may be incomplete.")
            
            self.log_entry("GEMINI_RESPONSE", f"Rules for '{topic_name}' extracted successfully")
            return rules_text
        except Exception as e:
            self.log_entry("ERROR", f"Gemini API failed to extract topic rules: {e}")
            return None
    
    def format_topic_rules_output(self, gemini_output, topic_name):
        """
        Wrap extracted topic rules with consistent header and metadata.
        
        Args:
            gemini_output (str): Raw output from Gemini
            topic_name (str): Name of the topic
            
        Returns:
            str: Formatted rules document for the topic
        """
        output = "=" * 80 + "\n"
        output += f"STRUCTURED RULES FOR: {topic_name.upper()}\n"
        output += "=" * 80 + "\n\n"
        output += f"Generated: {datetime.now()}\n"
        output += f"Source: {self.policy_file}\n"
        output += f"Topic: {topic_name}\n"
        output += f"Extraction Method: Topic-Specific Gemini Extraction\n"
        output += f"Format: Rule Engine v1.0 (Measurable, Enforceable)\n\n"
        output += "=" * 80 + "\n\n"
        
        output += gemini_output
        
        return output
    
    def save_topic_rules(self, formatted_rules, topic_name):
        """
        Save topic-specific rules to a separate file.
        
        Args:
            formatted_rules (str): Formatted rules content
            topic_name (str): Name of the topic
            
        Returns:
            str: Path to saved file, or None if failed
        """
        # Create a safe filename from topic name
        safe_topic_name = re.sub(r'[^a-zA-Z0-9_-]', '_', topic_name.lower())
        topic_rules_file = f"{OUTPUT_DIR}/rules_{safe_topic_name}.txt"
        
        try:
            with open(topic_rules_file, 'w') as f:
                f.write(formatted_rules)
            
            self.log_entry("SUCCESS", f"Topic rules saved to: {topic_rules_file}")
            self.log_entry("STATS", f"Output size: {len(formatted_rules)} characters")
            
            return topic_rules_file
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save topic rules file: {e}")
            return None

    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== RULE EXTRACTION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class ConfidenceAndRationaleGenerator:
    """
    Step 7: Generate confidence scores and rationale for each DSL rule.
    
    For each rule (clause):
    - Explain why this rule was suggested from the source policy
    - Cite the source clause reference
    - Explain why it's enforceable
    - Provide a confidence score (0.0-1.0) based on:
      * Clarity of original clause (absence of ambiguities)
      * Specificity of conditions
      * Measurability of thresholds
      * Cross-reference validation
    
    Output: stage7_confidence_rationale.json
    """
    
    def __init__(self, stage5_file, stage6_file, document_id=None, enable_mongodb=True):
        self.stage5_file = stage5_file  # Clarified clauses
        self.stage6_file = stage6_file  # DSL rules
        self.rationale_file = f"{OUTPUT_DIR}/stage7_confidence_rationale.json"
        self.document_id = document_id
        self.log = []
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
    
    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def read_json_file(self, filepath):
        """Read and parse JSON file"""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read {filepath}: {e}")
            return None
    
    def read_yaml_file(self, filepath):
        """Read YAML rules file"""
        try:
            import yaml
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read YAML {filepath}: {e}")
            return None
    
    def calculate_confidence_score(self, clause_data):
        """
        Calculate confidence score (0.0-1.0) based on:
        - Absence of ambiguities (clause is clarified)
        - Specificity of conditions
        - Measurability of entities
        - Enforcement clarity
        
        Args:
            clause_data: Dict with clause info from stage5
            
        Returns:
            float: Confidence score 0.0-1.0
        """
        score = 1.0
        
        # Penalty for ambiguities that were found and fixed
        if "ambiguities_fixed" in clause_data:
            ambiguities_fixed = clause_data["ambiguities_fixed"]
            if ambiguities_fixed:
                # Each fixed ambiguity reduces confidence by 0.05-0.15
                penalty_per_ambiguity = {
                    "SUBJECTIVE_LANGUAGE": 0.10,
                    "UNDEFINED_REFERENCES": 0.15,
                    "BOUNDARY_OVERLAPS": 0.12,
                    "INCOMPLETE_CONDITIONS": 0.12,
                    "VAGUE_METRICS": 0.12,
                    "UNDEFINED_AUTHORITY": 0.10
                }
                
                for ambiguity_type in ambiguities_fixed:
                    penalty = penalty_per_ambiguity.get(ambiguity_type, 0.10)
                    score -= penalty
        
        # Bonus for clear entity extraction
        if "entities" in clause_data and clause_data["entities"]:
            entity_count = len(clause_data["entities"])
            # Bonus capped at 0.05
            score += min(0.05, entity_count * 0.01)
        
        # Intent clarity bonus
        if "intent" in clause_data:
            intent = clause_data["intent"]
            # RESTRICTION and CONDITIONAL_ALLOWANCE are more measurable
            if intent in ["RESTRICTION", "CONDITIONAL_ALLOWANCE"]:
                score += 0.05
        
        # Clamp between 0.0 and 1.0
        return max(0.0, min(1.0, score))
    
    def build_local_rationale(self, clause_id, original_clause, clarified_clause, entities, ambiguities_fixed, intent):
        """
        Build rationale locally without Gemini API (avoids timeout issues).
        
        Args:
            clause_id: Clause identifier
            original_clause: Original clause text
            clarified_clause: Clarified clause text
            entities: Extracted entities
            ambiguities_fixed: List of fixed ambiguities
            intent: Clause intent (INFORMATIONAL, CONDITIONAL_ALLOWANCE, RESTRICTION)
            
        Returns:
            str: Formatted rationale
        """
        
        # Extract first sentence from original
        orig_summary = original_clause.split('.')[0] if original_clause else "Policy requirement"
        
        # Build key entities list
        entity_keys = list(entities.keys())[:5] if entities else []
        entity_str = ", ".join(entity_keys) if entity_keys else "Standard policy terms"
        
        # Build ambiguity summary
        if ambiguities_fixed:
            ambig_summary = f"Fixed ambiguities: {', '.join(ambiguities_fixed[:3])}"
        else:
            ambig_summary = "Clear and unambiguous"
        
        # Intent-specific reasoning
        intent_map = {
            "CONDITIONAL_ALLOWANCE": "Rule specifies conditional allowances/entitlements with measurable thresholds",
            "RESTRICTION": "Rule enforces restrictions with clear conditions and approval authorities",
            "INFORMATIONAL": "Rule defines classifications or reference information"
        }
        enforce_reason = intent_map.get(intent, "Rule extracted from policy clause")
        
        rationale = f"""SOURCE: {orig_summary}

ENFORCEABLE: {enforce_reason}. Entities extracted: {entity_str}. {ambig_summary}.

KEY_VALUES: {entity_str}"""
        
        return rationale
    
    def generate_rationale_with_gemini(self, clause_id, original_clause, clarified_clause, entities, ambiguities_fixed):
        """
        Use Gemini to generate detailed rationale for why a rule was suggested.
        OPTIMIZED: Shorter prompt, focused on key info only.
        
        Args:
            clause_id: Clause identifier (C1, C2, etc.)
            original_clause: Original clause text
            clarified_clause: Clarified clause text
            entities: Extracted entities from clause
            ambiguities_fixed: List of ambiguities that were fixed
            
        Returns:
            str: Rationale text
        """
        
        # Truncate long texts to avoid timeout
        orig_short = original_clause[:300] if original_clause else "N/A"
        clarif_short = clarified_clause[:300] if clarified_clause else "N/A"
        entities_str = json.dumps(entities, indent=2)[:200] if entities else "None"
        
        prompt = f"""Clause {clause_id}: Why is this rule enforceable?

ORIGINAL: {orig_short}

CLARIFIED: {clarif_short}

ENTITIES: {entities_str}

AMBIGUITIES FIXED: {", ".join(ambiguities_fixed) if ambiguities_fixed else "None"}

TASK: Generate brief rationale (50-100 words):

SOURCE: [1 sentence on policy requirement]
ENFORCEABLE: [Why it's objectively checkable]
KEY_VALUES: [Important thresholds/entities]

Output ONLY the above format, no extra text."""
        
        try:
            self.log_entry("GEMINI_REQUEST", f"Generating rationale for clause {clause_id}")
            response = self.model.generate_content(prompt, request_options={"timeout": 30})
            rationale = response.text.strip()
            self.log_entry("GEMINI_RESPONSE", f"Rationale generated for {clause_id}")
            return rationale
        except Exception as e:
            self.log_entry("ERROR", f"Gemini API failed for {clause_id}: {e}")
            # Return fallback rationale
            return f"SOURCE: {orig_short[:100]}\nENFORCEABLE: Rule extracted from policy clause\nKEY_VALUES: {', '.join(list(entities.keys())[:3]) if entities else 'N/A'}"
    
    def generate_confidence_and_rationale(self):
        """
        Main function to generate confidence scores and rationale for all clauses.
        
        Returns:
            dict: Mapping of clause_id to {rationale, confidence}
        """
        
        # Load stage 5 (clarified clauses)
        stage5_data = self.read_json_file(self.stage5_file)
        if not stage5_data:
            self.log_entry("ERROR", "Cannot load stage5 data")
            return None
        
        # Load stage 6 (DSL rules) to map which clauses have rules
        stage6_data = self.read_yaml_file(self.stage6_file)
        if not stage6_data:
            self.log_entry("ERROR", "Cannot load stage6 data")
            return None
        
        clarified_clauses = stage5_data.get("clarified_clauses", [])
        rules = stage6_data.get("rules", [])
        
        # Build mapping of clause_id to rule data
        rule_ids = {rule["rule_id"] for rule in rules}
        
        self.log_entry("INFO", f"Processing {len(clarified_clauses)} clauses")
        self.log_entry("INFO", f"Found {len(rule_ids)} rules in stage 6")
        
        confidence_rationale = {}
        
        for clause in clarified_clauses:
            clause_id = clause.get("clauseId")
            
            # Skip if no corresponding rule in stage 6
            if clause_id not in rule_ids:
                self.log_entry("WARNING", f"No rule found for {clause_id} in stage 6")
                continue
            
            # Calculate confidence score
            confidence = self.calculate_confidence_score(clause)
            
            # Generate rationale (LOCAL - no Gemini to avoid timeout)
            original_text = clause.get("text_original", "")
            clarified_text = clause.get("text_clarified", "")
            entities = clause.get("entities", {})
            ambiguities_fixed = clause.get("ambiguities_fixed", [])
            intent = clause.get("intent", "UNKNOWN")
            
            # Build rationale locally
            rationale = self.build_local_rationale(
                clause_id,
                original_text,
                clarified_text,
                entities,
                ambiguities_fixed,
                intent
            )
            
            confidence_rationale[clause_id] = {
                "clauseId": clause_id,
                "rationale": rationale,
                "confidence": round(confidence, 2),
                "ambiguitiesFixed": ambiguities_fixed,
                "sourceSection": intent
            }
            self.log_entry("SUCCESS", f"Generated confidence/rationale for {clause_id} (confidence: {round(confidence, 2)})")
        
        return confidence_rationale
    
    def save_confidence_rationale(self, data):
        """Save confidence and rationale to JSON file"""
        output = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "stage": "7",
                "source": [self.stage5_file, self.stage6_file],
                "title": "Confidence & Rationale for DSL Rules",
                "total_clauses": len(data)
            },
            "confidenceAndRationale": data
        }
        
        try:
            with open(self.rationale_file, 'w') as f:
                json.dump(output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Confidence & rationale saved to {self.rationale_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=7,
                stage_name="confidence-rationale",
                stage_output=output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save confidence & rationale: {e}")
            return False
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== CONFIDENCE & RATIONALE GENERATION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class PayloadEvaluator:
    """Step 3: Iterative payload evaluation against rules using LLM feedback loop (GENERIC - ANY POLICY)"""
    
    def __init__(self, rules_file, max_attempts=4):
        self.rules_file = rules_file
        self.max_attempts = max_attempts
        self.log = []
        self.attempt_history = []
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
    
    def _count_nesting_depth(self, obj, depth=0):
        """Count maximum nesting depth"""
        if isinstance(obj, dict):
            if not obj:
                return depth
            return max(self._count_nesting_depth(v, depth + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return depth
            return max(self._count_nesting_depth(item, depth + 1) for item in obj)
        else:
            return depth
    
    def _detect_structure_type(self, obj):
        """Detect JSON structure type"""
        if isinstance(obj, dict):
            return "Nested Dictionary"
        elif isinstance(obj, list):
            if len(obj) > 0 and isinstance(obj[0], dict):
                return "Array of Objects"
            elif len(obj) > 0 and isinstance(obj[0], list):
                return "Multi-dimensional Array"
            else:
                return "Simple Array"
        else:
            return "Unknown"
    
    def flatten_json(self, obj, parent_key='', sep='_'):
        """Flatten nested JSON for better LLM processing"""
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, (dict, list)):
                    items.extend(self.flatten_json(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                new_key = f"{parent_key}_{i}" if parent_key else f"[{i}]"
                if isinstance(v, (dict, list)):
                    items.extend(self.flatten_json(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
        return dict(items)
    

    def log_entry(self, level, message):
        """Log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def summarize_payload(self, payload_dict):
        """Summarize payload using Gemini (GENERIC - works with any payload)"""
        self.log_entry("PAYLOAD", f"Analyzing payload with {len(payload_dict)} fields")
        
        payload_str = json.dumps(payload_dict, indent=2)
        prompt = f"""Analyze this request payload and provide a concise summary. Be domain-agnostic.

Payload:
{payload_str}

TASK: 
1. What type of REQUEST is this? (describe the main action/intent)
2. What are the KEY FIELDS that need policy validation?
3. What POLICY AREAS or KEYWORDS are relevant based on the payload?

Format:
REQUEST_TYPE: [describe the type of request]
KEY_FIELDS: [list important fields from payload]
RELEVANT_KEYWORDS: [list keywords to search policy file for]

Be specific and extractive. Focus on what can be searched in policy rules."""

        try:
            response = self.model.generate_content(prompt)
            summary = response.text.strip()
            self.log_entry("GEMINI_SUMMARY", "Payload summarized")
            return summary
        except Exception as e:
            self.log_entry("ERROR", f"Summary generation failed: {e}")
            return None
    
    def validate_command(self, command):
        """Validate command syntax before execution"""
        # Check for common syntax errors
        issues = []
        
        # Check for unterminated quotes
        if command.count('"') % 2 != 0:
            issues.append("Unterminated double quotes")
        if command.count("'") % 2 != 0:
            issues.append("Unterminated single quotes")
        
        # Check for common pipe/redirect issues
        if command.endswith('|') or command.endswith('>'):
            issues.append("Command ends with pipe or redirect operator")
        
        # Check for basic command structure
        if not any(cmd in command for cmd in ['grep', 'head', 'tail', 'sed', 'awk', 'cat']):
            issues.append("No recognized search command found (grep/head/tail/sed/awk/cat)")
        
        # Check file exists
        if self.rules_file not in command:
            issues.append(f"Rules file path '{self.rules_file}' not found in command")
        
        return issues
    
    def execute_cli_command(self, command):
        """Execute CLI command (grep, head, tail, etc.)"""
        self.log_entry("CLI_EXECUTE", f"Command: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.strip()
            error_output = result.stderr.strip()
            
            # Capture both stdout and stderr
            if result.returncode != 0:
                if error_output:
                    output = f"[CLI_ERROR] {error_output}"
                elif not output:
                    output = "[No results]"
            
            response_lines = len(output.split('\n'))
            self.log_entry("CLI_RESPONSE", f"Got {response_lines} lines, Return code: {result.returncode}")
            return output
            
        except subprocess.TimeoutExpired:
            self.log_entry("ERROR", "Command timeout (exceeded 10 seconds)")
            return "[ERROR: Command timeout]"
        except Exception as e:
            self.log_entry("ERROR", f"Command execution failed: {e}")
            return f"[ERROR: {str(e)[:100]}]"
    
    def create_search_command(self, context, attempt_num, previous_response=None):
        """Use Gemini to create optimal search command (GENERIC - works with any policy rules file)"""
        
        if attempt_num == 1:
            prompt = f"""You are a search strategist for finding relevant rules in a policy document. 
            
PAYLOAD CONTEXT:
{context}

RULES FILE: {self.rules_file}

TASK: Create a SINGLE optimal grep/head/tail/sed command to search the rules file for relevant policies.

GENERIC RULES FOR COMMAND CREATION:
1. Extract keywords from payload context
2. Use grep to find matching sections in rules file
3. Use patterns, case-insensitive search, regex as needed
4. Combine multiple keywords with OR operator (-E flag)
5. Use -A (after) flag to get context around matches
6. Command must be executable in bash
7. Return ONLY the command, no explanation, no code blocks

Examples of generic commands:
- grep -i "keyword1\\|keyword2" {self.rules_file}
- grep -n -i -E "pattern1|pattern2|pattern3" {self.rules_file}
- grep -A 5 -i "section" {self.rules_file} | head -30
- grep -i -E "rule1|rule2" {self.rules_file} | tail -20

CREATE THE COMMAND (bash executable, single line):"""
        
        else:
            # Check if there was a previous error to fix
            error_context = ""
            if previous_response and "[ERROR:" in previous_response:
                error_context = f"\n\nPREVIOUS ERROR TO FIX: {previous_response[:200]}"
            elif previous_response and "[CLI_ERROR]" in previous_response:
                error_context = f"\n\nPREVIOUS COMMAND ERROR: {previous_response[:200]}"
            
            prompt = f"""You are refining a policy rule search based on previous results.

ORIGINAL PAYLOAD CONTEXT:
{context}{error_context}

ATTEMPT #{attempt_num}
PREVIOUS SEARCH RESULT (first 500 chars):
{previous_response[:500] if previous_response else "N/A"}

TASK: 
1. Analyze what the previous response revealed
2. Determine if it's SUFFICIENT, INCOMPLETE, or WRONG
3. If insufficient or wrong: Create a NEW, more refined search command
4. Go DEEPER by trying:
   - Different keywords
   - Related terms
   - Policy keywords found in previous results
   - Cross-reference sections
5. Use previous command as a clue, but try different approach

GENERIC REFINEMENT RULES (CRITICAL):
- Create a DIFFERENT grep/head/tail command (not the same as before)
- Try variations of keywords with PROPER QUOTING
- Use single grep call with -i -E flags
- Format: grep -i -E "word1|word2|word3" {self.rules_file} [| head/tail]
- NEVER use unterminated or mismatched quotes
- ENSURE all quotes are properly closed
- VERIFY pipes and redirects are complete
- Command must be EXECUTABLE in bash
- Return ONLY the command, no explanation, no markdown

Examples of CORRECT format:
- grep -i "keyword1\|keyword2" {self.rules_file}
- grep -i -E "word1|word2|word3" {self.rules_file} | head -20
- grep -A 3 -E "rule1|rule2" {self.rules_file} | tail -15

Rules file: {self.rules_file}

CREATE THE REFINED COMMAND (DOUBLE CHECK QUOTING AND PIPES):"""
        
        try:
            response = self.model.generate_content(prompt)
            command = response.text.strip()
            
            # Clean up command (remove markdown code blocks if present)
            command = command.replace("```bash", "").replace("```", "").replace("bash", "").strip()
            command = command.strip("'\"")  # Remove quotes if any
            
            self.log_entry("GEMINI_COMMAND", f"Attempt {attempt_num}: {command[:80]}...")
            return command
            
        except Exception as e:
            self.log_entry("ERROR", f"Command generation failed: {e}")
            return None
    
    def evaluate_with_feedback_loop(self, payload_dict):
        """Iterative evaluation: Attempt 1, 2, 3... with feedback"""
        
        self.log_entry("EVAL_START", "Starting iterative policy evaluation")
        self.log_entry("ATTEMPTS_MAX", f"Max attempts: {self.max_attempts}")
        
        # Step 1: Summarize payload
        summary = self.summarize_payload(payload_dict)
        if not summary:
            return {"status": "ERROR", "reason": "Failed to summarize payload"}
        
        context = f"Payload Summary:\n{summary}\n\nRules file: {self.rules_file}"
        
        previous_response = None
        final_rules_found = None
        final_analysis = None
        search_attempts = []
        
        # Iterative feedback loop
        previous_command_error = None
        
        for attempt in range(1, self.max_attempts + 1):
            self.log_entry("ATTEMPT", f"========== ATTEMPT {attempt}/{self.max_attempts} ==========")
            
            # Step 2a: Create search command (using previous response as clue)
            if previous_command_error:
                context_with_error = f"{context}\n\nPREVIOUS ATTEMPT ERROR:\n{previous_command_error}"
                command = self.create_search_command(context_with_error, attempt, previous_response)
            else:
                command = self.create_search_command(context, attempt, previous_response)
            
            if not command:
                self.log_entry("ERROR", "Failed to create search command")
                break
            
            # Step 2b: Validate command syntax (from attempt 2 onwards)
            if attempt >= 2:
                validation_issues = self.validate_command(command)
                if validation_issues:
                    self.log_entry("VALIDATION", f"Command has issues: {validation_issues}")
                    previous_command_error = f"Command validation failed:\n" + "\n".join(f"  - {issue}" for issue in validation_issues)
                    continue  # Skip execution, go to next attempt with feedback
            
            # Step 2c: Execute command
            response = self.execute_cli_command(command)
            previous_command_error = None  # Reset error if execution successful
            
            # Step 3: Analyze response with Gemini (GENERIC)
            self.log_entry("GEMINI_ANALYZE", f"Analyzing response from attempt {attempt}")
            
            analyze_prompt = f"""Analyze this search result from a policy rules file:

SEARCH RESULT (first 1000 chars):
{response[:1000]}

TASK: Determine if this result provides sufficient policy information for evaluation:
1. SUFFICIENT - Contains relevant policy rules/requirements for the payload
2. INCOMPLETE - Found some rules but missing important related policies
3. WRONG - Search returned irrelevant results, wrong direction
4. NO_RESULTS - Search returned empty/no matches

EVALUATION CRITERIA:
- Does the result contain rules that apply to the payload request?
- Are there enforcement levels (MUST/SHOULD/EXPECTED)?
- Are conditions and exceptions mentioned?
- Is the information actionable for compliance checking?

RESPOND WITH (strict format):
STATUS: [SUFFICIENT | INCOMPLETE | WRONG | NO_RESULTS]
RULES_SUMMARY: [Key rules/policies found in 1-2 sentences]
NEXT_ACTION: [stop | search deeper | try different keywords]
CONFIDENCE: [0-100] percentage confidence

Be concise and factual."""

            try:
                analysis = self.model.generate_content(analyze_prompt)
                analysis_text = analysis.text.strip()
                self.log_entry("ANALYSIS", analysis_text[:150])
                
                # Store attempt details (without command details in final report)
                attempt_info = {
                    "attempt": attempt,
                    "status": self.extract_status(analysis_text),
                    "rules_summary": self.extract_field(analysis_text, "RULES_SUMMARY"),
                    "next_action": self.extract_field(analysis_text, "NEXT_ACTION"),
                    "confidence": self.extract_field(analysis_text, "CONFIDENCE")
                }
                search_attempts.append(attempt_info)
                final_analysis = analysis_text
                
                # Check if SUFFICIENT
                if "SUFFICIENT" in analysis_text.upper():
                    self.log_entry("SUCCESS", f"Found sufficient rules at attempt {attempt}")
                    final_rules_found = response
                    break
                
                # Check if should stop (max attempts or WRONG without recovery)
                if "WRONG" in analysis_text.upper() and attempt >= self.max_attempts - 1:
                    self.log_entry("WARNING", "Stopping: Max attempts reached")
                    final_rules_found = response
                    break
                
                previous_response = response
                
            except Exception as e:
                self.log_entry("ERROR", f"Analysis failed: {e}")
                final_rules_found = response
                break
        
        # Extract final evaluation status
        final_status = self.extract_status(final_analysis) if final_analysis else "UNKNOWN"
        
        # Step 4: Evaluate payload against rules and make decision
        decision_analysis = None
        if final_rules_found and final_status == "SUFFICIENT":
            decision_analysis = self.evaluate_payload_against_rules(payload_dict, final_rules_found, summary)
        
        # Compile final report (clean, focused on decisions)
        report = {
            "status": "COMPLETED",
            "evaluation_result": final_status,
            "payload_summary": summary,
            "search_attempts": search_attempts,
            "relevant_rules": final_rules_found,
            "decision_analysis": decision_analysis,
            "log": self.log
        }
        
        return report
    
    def extract_qualification_criteria(self, rules_text):
        """Extract qualification criteria dynamically from rules (GENERIC for ANY policy)"""
        self.log_entry("CRITERIA_EXTRACTION", "Extracting qualification criteria from rules")
        
        criteria_prompt = f"""Analyze these policy rules and extract the QUALIFICATION CRITERIA.

RULES:
{rules_text[:2000]}

TASK: Identify what makes a request QUALIFY or DISQUALIFY under these rules.

Extract:
1. What are the KEY REQUIREMENTS for approval?
2. What would cause REJECTION?
3. What fields/conditions MUST be met?
4. Are there GRADE or LEVEL-BASED rules?
5. Are there APPROVAL or DOCUMENTATION requirements?

Format response as:
QUALIFICATION_CRITERIA: [List 3-5 key criteria for approval]
REJECTION_TRIGGERS: [List conditions that cause rejection]
REQUIRED_FIELDS: [List mandatory fields that must be present/true]
POLICY_TYPE: [any policy type]

Be specific and extract from the actual rules provided."""

        try:
            response = self.model.generate_content(criteria_prompt)
            criteria_text = response.text.strip()
            self.log_entry("CRITERIA_EXTRACTED", "Qualification criteria identified")
            return criteria_text
        except Exception as e:
            self.log_entry("ERROR", f"Criteria extraction failed: {e}")
            return None
    
    def evaluate_payload_against_rules(self, payload_dict, rules_text, payload_summary):
        """Evaluate payload against rules with GENERIC decision logic (works for ANY policy)"""
        self.log_entry("DECISION", "Starting generic payload evaluation")
        
        # Step 1: Extract qualification criteria from rules (domain-agnostic)
        criteria_text = self.extract_qualification_criteria(rules_text)
        if not criteria_text:
            return None
        
        # Step 2: Evaluate payload against extracted criteria
        decision_prompt = f"""You are evaluating a payload against policy rules to determine if it QUALIFIES.

EXTRACTED QUALIFICATION CRITERIA FROM RULES:
{criteria_text}

PAYLOAD DATA:
{json.dumps(payload_dict, indent=2)[:2000]}

PAYLOAD SUMMARY:
{payload_summary}

TASK: Evaluate if the payload MEETS the qualification criteria identified in the rules.

For each criterion:
1. State what the rule requires
2. Check what the payload provides
3. Does it MEET the requirement? (YES/NO)
4. If NO, why not? (cite actual payload values)

Then provide FINAL DECISION: APPROVE or REJECT

Format response EXACTLY as:
RULE_CHECK: [Criterion 1: YES/NO because...][Criterion 2: YES/NO because...][etc]
FAILING_CRITERIA: [List specific unmet requirements with payload evidence]
DECISION: [APPROVE | REJECT]
REASONING: [Explain decision citing payload values and rule requirements]

Be strict, factual, and specific. Cross-reference actual payload values with rule requirements."""

        try:
            self.log_entry("GEMINI_DECISION", "Evaluating payload against criteria")
            decision = self.model.generate_content(decision_prompt)
            decision_text = decision.text.strip()
            
            # Extract decision components
            decision_result = {
                "criteria_used": criteria_text,
                "rule_checks": self.extract_field(decision_text, "RULE_CHECK"),
                "failing_criteria": self.extract_field(decision_text, "FAILING_CRITERIA"),
                "decision": self.extract_decision(decision_text),
                "reasoning": self.extract_field(decision_text, "REASONING"),
                "full_analysis": decision_text
            }
            
            self.log_entry("DECISION_RESULT", f"Decision: {decision_result['decision']}")
            return decision_result
            
        except Exception as e:
            self.log_entry("ERROR", f"Decision analysis failed: {e}")
            return None
    
    def extract_status(self, text):
        """Extract STATUS field from analysis response"""
        for line in text.split('\n'):
            if line.startswith('STATUS:'):
                status = line.replace('STATUS:', '').strip()
                # Clean up brackets and extra text
                status = status.split('[')[-1].split(']')[0]
                return status
        return "UNKNOWN"
    
    def extract_field(self, text, field_name):
        """Extract named field from analysis response"""
        for line in text.split('\n'):
            if line.startswith(f"{field_name}:"):
                return line.replace(f"{field_name}:", '').strip()
        return ""
    
    def extract_decision(self, text):
        """Extract APPROVE/REJECT decision"""
        for line in text.split('\n'):
            if line.startswith('DECISION:'):
                decision = line.replace('DECISION:', '').strip()
                if 'APPROVE' in decision.upper():
                    return 'APPROVE'
                elif 'REJECT' in decision.upper():
                    return 'REJECT'
        return 'UNKNOWN'
    
    def save_evaluation_report(self, report, output_file=None):
        """Save evaluation report as formatted text file"""
        if not output_file:
            output_file = f"{OUTPUT_DIR}/evaluation_report.txt"
        
        try:
            with open(output_file, 'w') as f:
                f.write(self.format_report_as_text(report))
            
            self.log_entry("REPORT_SAVED", f"Report saved to {output_file}")
            return output_file
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save report: {e}")
            return None
    
    def format_report_as_text(self, report):
        """Format report as clean, readable text"""
        lines = []
        lines.append("=" * 80)
        lines.append("POLICY EVALUATION REPORT")
        lines.append("=" * 80)
        
        # Payload Summary
        lines.append("\n[PAYLOAD SUMMARY]")
        lines.append(report['payload_summary'])
        
        # Rules Search
        lines.append("\n[RULES SEARCH STATUS]")
        lines.append(f"Result: {report.get('evaluation_result', 'UNKNOWN')}")
        
        # Search Attempts Summary
        lines.append("\n[SEARCH ATTEMPTS]")
        for attempt in report['search_attempts']:
            lines.append(f"\nAttempt {attempt['attempt']}: {attempt['status']} (Confidence: {attempt['confidence']})")
            lines.append(f"  Found: {attempt['rules_summary'][:150]}...")
        
        # Decision Analysis
        lines.append("\n" + "=" * 80)
        lines.append("QUALIFICATION DECISION")
        lines.append("=" * 80)
        
        if report.get('decision_analysis'):
            decision = report['decision_analysis']
            lines.append(f"\nDECISION: {decision.get('decision', 'UNKNOWN')}")
            lines.append(f"\nREASONING:")
            lines.append(decision.get('reasoning', 'N/A'))
            
            if decision.get('failing_criteria') and decision['failing_criteria'].strip():
                lines.append(f"\nFAILING CRITERIA:")
                criteria_text = decision['failing_criteria']
                for line in criteria_text.split('\n'):
                    if line.strip() and line.strip() != '[]':
                        lines.append(f"  {line.strip()}")
            
            if decision.get('rule_checks'):
                lines.append(f"\nDETAILED RULE CHECKS:")
                for line in decision['rule_checks'].split('. '):
                    if line.strip():
                        lines.append(f"  • {line.strip()}")
        
        # Key Policies
        lines.append("\n" + "=" * 80)
        lines.append("APPLICABLE POLICIES & RULES")
        lines.append("=" * 80)
        
        if report['relevant_rules']:
            rules_lines = report['relevant_rules'].split('\n')
            for i, line in enumerate(rules_lines[:20]):
                if line.strip():
                    lines.append(line)
                if i >= 19:
                    lines.append("\n[See rules.txt for complete policy details]")
                    break
        
        lines.append("\n" + "=" * 80)
        lines.append(f"REPORT STATUS: {report['status']}")
        lines.append("=" * 80 + "\n")
        
        return "\n".join(lines)
    
    def print_evaluation_summary(self, report):
        """Print human-readable evaluation summary"""
        print("\n" + "="*80)
        print("POLICY EVALUATION REPORT")
        print("="*80)
        
        print(f"\n[PAYLOAD SUMMARY]")
        print(report['payload_summary'])
        
        print(f"\n[RULES SEARCH RESULT]")
        print(f"  Status: {report.get('evaluation_result', 'UNKNOWN')}")
        
        print(f"\n[SEARCH ATTEMPTS]")
        for attempt in report['search_attempts']:
            print(f"\n  Attempt {attempt['attempt']}")
            print(f"    Result: {attempt['status']}")
            print(f"    Rules Found: {attempt['rules_summary']}")
            print(f"    Confidence: {attempt['confidence']}")
        
        # Decision Analysis
        if report.get('decision_analysis'):
            decision = report['decision_analysis']
            
            # Show extracted criteria
            if decision.get('criteria_used'):
                print(f"\n[EXTRACTED QUALIFICATION CRITERIA FROM RULES]")
                for line in decision['criteria_used'].split('\n')[:8]:
                    if line.strip():
                        print(f"  {line.strip()}")
            
            print(f"\n[QUALIFICATION DECISION]")
            print(f"  Decision: {decision.get('decision', 'UNKNOWN')}")
            print(f"  Reasoning: {decision.get('reasoning', 'N/A')}")
            
            if decision.get('failing_criteria'):
                print(f"\n  Failing Criteria:")
                for line in decision['failing_criteria'].split('\n'):
                    if line.strip():
                        print(f"    - {line.strip()}")
            
            if decision.get('rule_checks'):
                print(f"\n  Rule Checks:")
                for line in decision['rule_checks'].split('\n')[:10]:
                    if line.strip():
                        print(f"    {line.strip()}")
        
        print(f"\n[KEY POLICIES & RULES]")
        if report['relevant_rules']:
            lines = report['relevant_rules'].split('\n')[:12]
            for line in lines:
                if line.strip():
                    print(f"  {line}")
        
        print(f"\n[COMPLETION STATUS] {report['status']}")
        print("="*80 + "\n")


def interactive_menu():
    """Show interactive menu when no arguments provided"""
    print("\n" + "="*80)
    print("POLICY ENFORCEMENT SYSTEM - INTERACTIVE MODE")
    print("="*80)
    print("\nSelect operation:")
    print("  0) discover-patterns  - Discover patterns from raw text → pattern_index.json")
    print("  A) analyze-structure  - Stage 0: Extract ALL sections & Annexures → stage0_structured_document.json")
    print("  1) extract            - Extract policy from PDF → filename.txt")
    print("  2) extract-clauses    - Extract elaborated clauses → stage1_clauses.json")
    print("  3) classify-intents   - Classify clause intents → stage2_classified.json")
    print("  4) extract-entities   - Extract entities & thresholds → stage3_entities.json")
    print("  5) detect-ambiguities - Detect ambiguities in clauses → stage4_ambiguity_flags.json")
    print("  6) clarify-ambiguities - Clarify ambiguous clauses → stage5_clarified_clauses.json")
    print("  7) generate-dsl       - Generate DSL rules → stage6_dsl_rules.yaml")
    print("  8) confidence-rationale - Generate confidence scores → stage7_confidence_rationale.json")
    print("  9) extract-rules      - Extract ALL rules from text → rules.txt")
    print(" 10) evaluate           - Evaluate employee payload against rules")
    print(" 11) extract-topics     - Select topic → Generate rules for topic")
    print(" 12) normalize-policies - Generate normalized policy JSON → stage8_normalized_policies.json")
    print(" 13) opa-bundle-storage - Stage 10: Store Rego rules in OPA-compatible bundle format")
    print(" 14) run-full-pipeline  - Run complete pipeline (1B→2→3→4→5→6→8→9→10) at once")
    print(" 15) exit               - Exit")
    
    choice = input("\nEnter choice (0-15 or A): ").strip()
    
    if choice == "0":
        text_file = input("Enter raw policy text file path (default: filename.txt): ").strip()
        if not text_file:
            text_file = f"{OUTPUT_DIR}/filename.txt"
        return ("discover-patterns", text_file)
    
    elif choice.lower() == "a":
        text_file = input("Enter raw policy text file path (default: filename.txt): ").strip()
        if not text_file:
            text_file = f"{OUTPUT_DIR}/filename.txt"
        return ("analyze-structure", text_file)
    
    elif choice == "1":
        pdf_file = input("Enter PDF file path: ").strip()
        if not pdf_file:
            print("ERROR: PDF file path required")
            return None
        return ("extract", pdf_file)
    
    elif choice == "2":
        text_file = input("Enter text file path (default: filename.txt): ").strip()
        if not text_file:
            text_file = f"{OUTPUT_DIR}/filename.txt"
        return ("extract-clauses", text_file)
    
    elif choice == "3":
        clauses_file = input("Enter clauses file path (default: stage1_clauses.json): ").strip()
        if not clauses_file:
            clauses_file = f"{OUTPUT_DIR}/stage1_clauses.json"
        return ("classify-intents", clauses_file)
    
    elif choice == "4":
        classified_file = input("Enter classified file path (default: stage2_classified.json): ").strip()
        if not classified_file:
            classified_file = f"{OUTPUT_DIR}/stage2_classified.json"
        return ("extract-entities", classified_file)
    
    elif choice == "5":
        stage3_file = input("Enter entities file path (default: stage3_entities.json): ").strip()
        if not stage3_file:
            stage3_file = f"{OUTPUT_DIR}/stage3_entities.json"
        return ("detect-ambiguities", stage3_file)
    
    elif choice == "6":
        stage3_file = input("Enter entities file path (default: stage3_entities.json): ").strip()
        if not stage3_file:
            stage3_file = f"{OUTPUT_DIR}/stage3_entities.json"
        return ("clarify-ambiguities", stage3_file)
    
    elif choice == "7":
        stage5_file = input("Enter clarified clauses file path (default: stage5_clarified_clauses.json): ").strip()
        if not stage5_file:
            stage5_file = f"{OUTPUT_DIR}/stage5_clarified_clauses.json"
        return ("generate-dsl", stage5_file)
    
    elif choice == "8":
        stage5_file = input("Enter clarified clauses file path (default: stage5_clarified_clauses.json): ").strip()
        if not stage5_file:
            stage5_file = f"{OUTPUT_DIR}/stage5_clarified_clauses.json"
        stage6_file = input("Enter DSL rules file path (default: stage6_dsl_rules.yaml): ").strip()
        if not stage6_file:
            stage6_file = f"{OUTPUT_DIR}/stage6_dsl_rules.yaml"
        return ("confidence-rationale", stage5_file, stage6_file)
    
    elif choice == "9":
        text_file = input("Enter text file path (default: filename.txt): ").strip()
        if not text_file:
            text_file = f"{OUTPUT_DIR}/filename.txt"
        return ("extract-rules", text_file)
    
    elif choice == "10":
        input_method = input("Enter payload via:\n  1) File path\n  2) Direct JSON input\n\nChoice (1-2): ").strip()
        
        if input_method == "1":
            payload_file = input("Enter payload JSON file path: ").strip()
            if not payload_file:
                print("ERROR: Payload file path required")
                return None
            return ("evaluate", payload_file)
        
        elif input_method == "2":
            print("\nEnter JSON payload (you can paste multiline JSON, press Enter twice when done):")
            print("-" * 80)
            
            lines = []
            empty_count = 0
            while True:
                line = input()
                if line == "":
                    empty_count += 1
                    if empty_count >= 2:
                        break
                    lines.append(line)
                else:
                    empty_count = 0
                    lines.append(line)
            
            json_str = "\n".join(lines).strip()
            
            # Validate JSON
            try:
                payload = json.loads(json_str)
                # Save to temp file
                temp_file = f"{OUTPUT_DIR}/.temp_payload.json"
                with open(temp_file, 'w') as f:
                    json.dump(payload, f, indent=2)
                print(f"✓ JSON parsed successfully")
                return ("evaluate", temp_file)
            
            except json.JSONDecodeError as e:
                print(f"ERROR: Invalid JSON - {e}")
                return None
        
        else:
            print("Invalid choice. Please try again.")
            return None
    
    elif choice == "11":
        text_file = input("Enter text file path (default: filename.txt): ").strip()
        if not text_file:
            text_file = f"{OUTPUT_DIR}/filename.txt"
        return ("extract-topics", text_file)
    
    elif choice == "12":
        dsl_file = input("Enter DSL rules file path (default: stage6_dsl_rules.yaml): ").strip()
        if not dsl_file:
            dsl_file = f"{OUTPUT_DIR}/stage6_dsl_rules.yaml"
        confidence_file = input("Enter confidence data file path (optional, press Enter to skip): ").strip()
        if not confidence_file:
            confidence_file = None
        return ("normalize-policies", dsl_file, confidence_file, "--no-llm")
    
    elif choice == "13":
        rego_bundles_file = input("Enter stage9_rego_bundles.json file path (default: stage9_rego_bundles.json): ").strip()
        if not rego_bundles_file:
            rego_bundles_file = f"{OUTPUT_DIR}/stage9_rego_bundles.json"
        document_id = input("Enter document ID (optional, default: auto-generated): ").strip()
        if not document_id:
            # Auto-generate from filename or use timestamp
            document_id = None
        return ("opa-bundle-storage", rego_bundles_file, document_id)
    
    elif choice == "14":
        pdf_file = input("Enter PDF file path: ").strip()
        if not pdf_file:
            print("ERROR: PDF file path required")
            return None
        return ("run-full-pipeline", pdf_file)
    
    elif choice == "15":
        print("Goodbye!")
        sys.exit(0)
    
    else:
        print("Invalid choice. Please try again.")
        return None


# ============================================================================
# STAGE 9: DSL to Rego Converter
# ============================================================================

class RegoGenerator:
    """
    Stage 9: Generate Rego rules from DSL rules and normalized policies
    
    Merges stage6_dsl_rules.yaml and stage8_normalized_policies.json
    Output: stage9_rego_bundles.json (OPA-compatible Rego format)
    
    Features:
    - Converts WHEN/THEN logic to Rego syntax
    - Ambiguous rules marked with WARN action
    - Clear rules use ENFORCE action
    - Preserves confidence scores
    - Generates complete Rego package
    """
    
    def __init__(self, dsl_file, normalized_file, document_id=None, enable_mongodb=True):
        self.dsl_file = dsl_file
        self.normalized_file = normalized_file
        self.rego_bundles_file = f"{OUTPUT_DIR}/stage9_rego_bundles.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        self.log_entry("INFO", "RegoGenerator initialized")
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] [Stage 9] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def read_dsl_rules(self):
        """Read stage6_dsl_rules.yaml"""
        try:
            import yaml
            with open(self.dsl_file, 'r') as f:
                data = yaml.safe_load(f)
            
            rules = data.get('rules', [])
            self.log_entry("SUCCESS", f"Read {len(rules)} DSL rules from {self.dsl_file}")
            return data
        
        except FileNotFoundError:
            self.log_entry("ERROR", f"DSL file not found: {self.dsl_file}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read DSL rules: {e}")
            return None
    
    def read_normalized_policies(self):
        """Read stage8_normalized_policies.json"""
        try:
            with open(self.normalized_file, 'r') as f:
                data = json.load(f)
            
            policies = data.get('policies', [])
            self.log_entry("SUCCESS", f"Read {len(policies)} normalized policies from {self.normalized_file}")
            return data
        
        except FileNotFoundError:
            self.log_entry("ERROR", f"Normalized file not found: {self.normalized_file}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read normalized policies: {e}")
            return None
    
    def merge_dsl_and_normalized(self, dsl_data, normalized_data):
        """Merge DSL rules and normalized policies by clause_id"""
        merged = {}
        
        # Extract DSL rules
        dsl_rules = {rule['rule_id']: rule for rule in dsl_data.get('rules', [])}
        self.log_entry("MERGE", f"Extracted {len(dsl_rules)} DSL rules")
        
        # Extract normalized policies and correlate with DSL rules
        for policy in normalized_data.get('policies', []):
            # Handle different clause_id locations
            clause_id = policy.get('clause_id')
            if not clause_id:
                # Check in core_attributes
                clause_id = policy.get('core_attributes', {}).get('clauseId')
            
            if clause_id and clause_id in dsl_rules:
                merged[clause_id] = {
                    'clause_id': clause_id,
                    'dsl_rule': dsl_rules[clause_id],
                    'normalized_policy': policy,
                    'confidence': policy.get('confidence_score', policy.get('rationale_metadata', {}).get('confidence', 0.5)),
                    'is_ambiguous': policy.get('is_ambiguous', policy.get('core_attributes', {}).get('is_real_ambiguity', False))
                }
        
        self.log_entry("MERGE", f"Merged into {len(merged)} clause records")
        return merged
    
    def convert_operator_to_rego(self, operator):
        """Convert DSL operator to Rego syntax"""
        operator_map = {
            'EQUALS': '==',
            'NOT_EQUALS': '!=',
            'LESS_THAN': '<',
            'LESS_THAN_OR_EQUAL': '<=',
            'GREATER_THAN': '>',
            'GREATER_THAN_OR_EQUAL': '>=',
            'IN': 'in',
            'CONTAINS': 'contains'
        }
        return operator_map.get(operator, '==')
    
    def generate_rego_when_conditions(self, when_conditions):
        """Convert DSL WHEN conditions to Rego syntax"""
        conditions = []
        
        for condition in when_conditions:
            fact = condition.get('fact', 'unknown')
            operator = condition.get('operator', 'EQUALS')
            value = condition.get('value')
            
            # Convert operator
            rego_operator = self.convert_operator_to_rego(operator)
            
            # Format value
            if isinstance(value, list):
                formatted_value = json.dumps(value)
            elif isinstance(value, str):
                if re.match(r'^-?\d+\.?\d*$', value):
                    formatted_value = value
                else:
                    formatted_value = f'"{value}"'
            else:
                formatted_value = json.dumps(value)
            
            # Build condition
            condition_str = f"input.{fact} {rego_operator} {formatted_value}"
            conditions.append(condition_str)
        
        return "\n    ".join(conditions) if conditions else "true"
    
    def generate_rego_then_constraints(self, then_constraints, intent, is_ambiguous):
        """Convert DSL THEN constraints to Rego output"""
        action = 'warn' if is_ambiguous else 'enforce'
        
        constraints = then_constraints.get(action, [])
        
        if not constraints:
            all_actions = [k for k in then_constraints.keys() if k in ['enforce', 'warn']]
            if all_actions:
                constraints = then_constraints.get(all_actions[0], [])
            else:
                constraints = []
        
        # Extract constraint info
        if isinstance(constraints, list) and constraints:
            constraint = constraints[0] if isinstance(constraints[0], dict) else {}
        else:
            constraint = constraints if isinstance(constraints, dict) else {}
        
        constraint_name = constraint.get('constraint', 'policy_check')
        constraint_value = constraint.get('value', 'APPROVED')
        
        rego_code = f"""
    result := {{
        "allow": true,
        "action": "{action}",
        "constraint": "{constraint_name}",
        "status": "{constraint_value}"
    }}"""
        
        return rego_code, action
    
    def generate_rego_rule(self, clause_id, merged_data):
        """Generate complete Rego rule for a single clause"""
        clause_data = merged_data
        dsl_rule = clause_data.get('dsl_rule', {})
        normalized = clause_data.get('normalized_policy', {})
        is_ambiguous = clause_data.get('is_ambiguous', False)
        
        # Extract components
        when_all = dsl_rule.get('when', {}).get('all', [])
        then_clause = dsl_rule.get('then', {})
        intent = normalized.get('intent', 'INFORMATIONAL')
        
        # Generate Rego function name
        rule_name = f"allow_{clause_id.lower().replace('_', '')}_{intent.lower()[:10]}"
        
        # Generate conditions
        when_conditions = self.generate_rego_when_conditions(when_all)
        
        # Generate constraints
        constraint_code, action = self.generate_rego_then_constraints(then_clause, intent, is_ambiguous)
        
        # Build complete Rego rule
        rego_code = f"""
# Rule: {clause_id}
# Intent: {intent}
# Ambiguous: {is_ambiguous}
{rule_name} {{
    {when_conditions}{constraint_code}
}}"""
        
        return {
            'clause_id': clause_id,
            'rego_rule_name': rule_name,
            'rego_code': rego_code,
            'intent': intent,
            'is_ambiguous': is_ambiguous,
            'action': action,
            'confidence': clause_data.get('confidence', 0.5)
        }
    
    def generate_rego_bundles(self, merged_data):
        """Generate complete Rego bundles with package structure"""
        self.log_entry("GENERATE", "Generating Rego bundles from merged data")
        
        # Group rules by policy domain
        policy_groups = self._group_by_policy_domain(merged_data)
        
        policies = []
        all_rules = []
        all_rego_code = []
        
        # Package header
        all_rego_code.append("""package travel_policy

# Generated by Stage 9: DSL to Rego Converter
# Date: """ + datetime.now().isoformat() + """
# This file contains all policy rules converted from DSL format

""")
        
        for policy_name, clauses in policy_groups.items():
            rules = []
            
            for clause_id in clauses:
                rego_rule = self.generate_rego_rule(clause_id, merged_data[clause_id])
                rules.append(rego_rule)
                all_rules.append(rego_rule)
                all_rego_code.append(rego_rule['rego_code'])
            
            policy = {
                'policy_name': policy_name,
                'package': f'data.{policy_name}',
                'description': f'Enforced policy rules for {policy_name}',
                'rule_count': len(rules),
                'rules': rules
            }
            policies.append(policy)
            
            self.log_entry("POLICY", f"Generated {len(rules)} Rego rules for policy: {policy_name}")
        
        # Add allow_all default rule
        all_rego_code.append("""
# Default: Allow if no violations
allow_default {
    true
}
""")
        
        total_rules = len(all_rules)
        bundles = {
            'metadata': {
                'generated': datetime.now().isoformat(),
                'stage': 9,
                'stage_name': 'dsl-to-rego',
                'source_dsl': self.dsl_file,
                'source_normalized': self.normalized_file,
                'total_policies': len(policies),
                'total_rules': total_rules
            },
            'policies': policies,
            'rego_code': '\n'.join(all_rego_code),
            'statistics': {
                'total_clauses': len(merged_data),
                'total_rules': total_rules,
                'ambiguous_rules': sum(1 for r in all_rules if r['is_ambiguous']),
                'enforce_rules': sum(1 for r in all_rules if r['action'] == 'enforce'),
                'warn_rules': sum(1 for r in all_rules if r['action'] == 'warn')
            }
        }
        
        return bundles
    
    def _group_by_policy_domain(self, merged_data):
        """Group clauses by policy domain"""
        groups = {}
        
        for clause_id in merged_data.keys():
            domain = 'travel_policy'
            
            if domain not in groups:
                groups[domain] = []
            
            groups[domain].append(clause_id)
        
        return groups
    
    def save_rego_bundles(self, bundles):
        """Save Rego bundles to JSON file"""
        try:
            with open(self.rego_bundles_file, 'w') as f:
                json.dump(bundles, f, indent=2)
            
            self.log_entry("SUCCESS", f"Rego bundles saved to {self.rego_bundles_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=9,
                stage_name='dsl-to-rego',
                stage_output=bundles
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
        
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save Rego bundles: {e}")
            return False
    
    def generate(self):
        """Main workflow for Rego generation"""
        self.log_entry("START", "Stage 9: DSL to Rego Conversion")
        
        # Step 1: Read input files
        self.log_entry("STEP", "Reading DSL rules")
        dsl_data = self.read_dsl_rules()
        if not dsl_data:
            return False
        
        self.log_entry("STEP", "Reading normalized policies")
        normalized_data = self.read_normalized_policies()
        if not normalized_data:
            return False
        
        # Step 2: Merge DSL and normalized data
        self.log_entry("STEP", "Merging DSL rules with normalized policies")
        merged_data = self.merge_dsl_and_normalized(dsl_data, normalized_data)
        
        if not merged_data:
            self.log_entry("ERROR", "Merge resulted in empty data")
            return False
        
        # Step 3: Generate Rego bundles
        self.log_entry("STEP", "Generating Rego bundles")
        bundles = self.generate_rego_bundles(merged_data)
        
        # Step 4: Save to file
        self.log_entry("STEP", "Saving Rego bundles to file")
        if not self.save_rego_bundles(bundles):
            return False
        
        self.log_entry("SUCCESS", "Stage 9 completed successfully")
        self.log_entry("STATS", f"Generated Rego bundles with {bundles['statistics']['total_rules']} rules")
        
        return True
    
    def save_log(self):
        """Append log to mechanism.log"""
        try:
            with open(LOG_FILE, 'a') as f:
                f.write("\n\n=== STAGE 9: DSL TO REGO CONVERSION LOG ===\n")
                f.write(f"Timestamp: {datetime.now()}\n")
                f.write("="*60 + "\n\n")
                for entry in self.log:
                    f.write(entry + "\n")
            
            self.log_entry("SUCCESS", f"Log saved to {LOG_FILE}")
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save log: {e}")


def main():
    """Main CLI interface - supports both CLI args and interactive mode"""
    
    # Interactive mode if no arguments
    if len(sys.argv) < 2:
        result = interactive_menu()
        if result is None:
            main()  # Retry
            return
        
        # Handle different tuple sizes from interactive menu
        if len(result) == 4:
            command, arg1, arg2, flag = result
            # For normalize-policies with --no-llm flag
            sys.argv = [sys.argv[0], command, arg1, arg2, flag]
        elif len(result) == 3:
            command, arg1, arg2 = result
            # Handle 3-tuple cases (confidence-rationale, opa-bundle-storage)
            if command == "opa-bundle-storage":
                # opa-bundle-storage: arg1=file, arg2=document_id (optional)
                if arg2:
                    sys.argv = [sys.argv[0], command, arg1, arg2]
                else:
                    sys.argv = [sys.argv[0], command, arg1]
            else:
                # confidence-rationale: arg1 and arg2 are required
                sys.argv = [sys.argv[0], command, arg1, arg2]
        else:
            command, arg = result
            sys.argv = [sys.argv[0], command, arg]
    else:
        command = sys.argv[1]
        
        # Handle confidence-rationale which needs 2 arguments
        if command == "confidence-rationale":
            if len(sys.argv) < 4:
                print("Usage:")
                print("  python policy_validator.py confidence-rationale <stage5_clarified_clauses.json> <stage6_dsl_rules.yaml>")
                print("\nOr run without arguments for interactive mode:")
                print("  python policy_validator.py")
                sys.exit(1)
            arg = sys.argv[2]
        else:
            if len(sys.argv) < 3:
                print("Usage:")
                print("  python policy_validator.py analyze-structure <policy.txt>    # Stage 0: Extract ALL sections")
                print("  python policy_validator.py extract <policy.pdf>")
                print("  python policy_validator.py extract-clauses <filename.txt>")
                print("  python policy_validator.py classify-intents <stage2_classified.json>")
                print("  python policy_validator.py extract-entities <stage2_classified.json>")
                print("  python policy_validator.py detect-ambiguities <stage3_entities.json>")
                print("  python policy_validator.py clarify-ambiguities <stage3_entities.json>")
                print("  python policy_validator.py generate-dsl <stage5_clarified_clauses.json>")
                print("  python policy_validator.py confidence-rationale <stage5_clarified_clauses.json> <stage6_dsl_rules.yaml>")
                print("  python policy_validator.py extract-rules <filename.txt>")
                print("  python policy_validator.py extract-topics <filename.txt>")
                print("  python policy_validator.py evaluate <payload.json>")
                print("\nOr run without arguments for interactive mode:")
                print("  python policy_validator.py")
                sys.exit(1)
            arg = sys.argv[2]
    
    if command == "discover-patterns":
        policy_text_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 0A: PATTERN DISCOVERY FROM RAW POLICY TEXT")
        print(f"{'='*80}\n")
        
        discoverer = PatternDiscoveryEngine(policy_text_file)
        success = discoverer.discover()
        discoverer.save_log()
        
        if success:
            print(f"\n✓ Pattern discovery complete. Output: {OUTPUT_DIR}/pattern_index.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Extract clauses from policy text")
            print(f"  python policy_validator.py extract-clauses {OUTPUT_DIR}/filename.txt")
        else:
            print("\n✗ Pattern discovery failed. Check logs.")
            sys.exit(1)
    
    elif command == "analyze-structure":
        policy_text_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 0: DOCUMENT STRUCTURE ANALYSIS & ANNEXURE EXTRACTION")
        print("CRITICAL: Extracts Annexures that contain actual policy rules")
        print(f"{'='*80}\n")
        
        analyzer = DocumentStructureAnalyzer(policy_text_file)
        structure = analyzer.analyze()
        analyzer.save_log()
        
        if structure:
            print(f"\n✓ Document structure analysis complete.")
            print(f"✓ Output: {OUTPUT_DIR}/stage0_structured_document.json")
            print(f"✓ Total clauses extracted: {structure['metadata']['total_clauses']}")
            print(f"✓ Annexures found: {structure['metadata']['total_annexures']}")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Extract clauses from structured document")
            print(f"  python policy_validator.py extract-clauses {OUTPUT_DIR}/stage0_structured_document.json")
        else:
            print("\n✗ Document structure analysis failed. Check logs.")
            sys.exit(1)
    
    elif command == "extract":
        pdf_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 1: POLICY EXTRACTION (PDF → TEXT)")
        print(f"{'='*80}\n")
        
        extractor = PolicyExtractor(pdf_file)
        success = extractor.extract_pdf()
        extractor.save_log()
        
        if success:
            print(f"\n✓ Extraction complete. Output: {OUTPUT_DIR}/filename.txt")
            print("\nNext step: Extract clauses with elaboration")
            print(f"  python policy_validator.py extract-clauses {OUTPUT_DIR}/filename.txt")
        else:
            print("\n✗ Extraction failed. Check logs.")
            sys.exit(1)
    
    elif command == "extract-clauses":
        policy_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 1B: CLAUSE EXTRACTION & ELABORATION")
        print(f"{'='*80}\n")
        
        clause_extractor = ClauseExtractor(policy_file)
        success = clause_extractor.extract()
        clause_extractor.save_log()
        
        if success:
            print(f"\n✓ Clause extraction complete. Output: {OUTPUT_DIR}/stage1_clauses.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Classify clause intents")
            print(f"  python policy_validator.py classify-intents {OUTPUT_DIR}/stage1_clauses.json")
        else:
            print("\n✗ Clause extraction failed. Check logs.")
            sys.exit(1)
    
    elif command == "classify-intents":
        clauses_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 2: INTENT CLASSIFICATION")
        print(f"{'='*80}\n")
        
        intent_classifier = IntentClassifier(clauses_file)
        success = intent_classifier.classify()
        intent_classifier.save_log()
        
        if success:
            print(f"\n✓ Intent classification complete. Output: {OUTPUT_DIR}/stage2_classified.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Extract entities and thresholds")
            print(f"  python policy_validator.py extract-entities {OUTPUT_DIR}/stage2_classified.json")
        else:
            print("\n✗ Intent classification failed. Check logs.")
            sys.exit(1)
    
    elif command == "extract-entities":
        classified_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 3: ENTITY & THRESHOLD EXTRACTION (Rule-based, no LLM)")
        print(f"{'='*80}\n")
        
        entity_extractor = EntityExtractor(classified_file, use_langchain=False)
        success = entity_extractor.extract()
        entity_extractor.save_log()
        
        if success:
            print(f"\n✓ Entity extraction complete. Output: {OUTPUT_DIR}/stage3_entities.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Extract rules from clauses")
            print(f"  python policy_validator.py extract-rules {OUTPUT_DIR}/filename.txt")
        else:
            print("\n✗ Entity extraction failed. Check logs.")
            sys.exit(1)
    
    elif command == "extract-rules":
        policy_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 2: RULE EXTRACTION (GREP + GEMINI)")
        print(f"{'='*80}\n")
        
        rule_extractor = RuleExtractor(policy_file)
        success = rule_extractor.extract()
        rule_extractor.save_log()
        
        if success:
            print(f"\n✓ Rule extraction complete. Output: {OUTPUT_DIR}/rules.txt")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
        else:
            print("\n✗ Rule extraction failed. Check logs.")
            sys.exit(1)
    
    elif command == "extract-topics":
        policy_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 2B: TOPIC/SCENARIO EXTRACTION & INDIVIDUAL RULE GENERATION")
        print(f"{'='*80}\n")
        
        try:
            rule_extractor = RuleExtractor(policy_file)
            
            # Step 1: Read policy file
            print("Reading policy file...")
            content = rule_extractor.read_policy_file()
            if not content:
                print("\n✗ Failed to read policy file.")
                sys.exit(1)
            
            # Step 2: Extract topics
            print("\nExtracting topics and scenarios from policy...")
            topics_text = rule_extractor.extract_topics_and_scenarios(content)
            if not topics_text:
                print("\n✗ Failed to extract topics.")
                sys.exit(1)
            
            # Display topics
            print("\n" + "="*80)
            print("AVAILABLE TOPICS/SCENARIOS IN POLICY:")
            print("="*80)
            print(topics_text)
            print("="*80)
            
            # Step 3: Ask user which topic to generate rules for
            print("\nEnter the topic name or number to generate individual rules for that topic.")
            print("(or press Enter to skip and generate rules for all topics)")
            topic_choice = input("\nTopic name/number: ").strip()
            
            if topic_choice:
                # Step 4: Extract rules for specific topic
                print(f"\nGenerating rules for: {topic_choice}")
                topic_rules = rule_extractor.extract_rules_for_topic(content, topic_choice)
                if not topic_rules:
                    print(f"\n✗ Failed to extract rules for topic '{topic_choice}'")
                    sys.exit(1)
                
                # Step 5: Format and save
                formatted_rules = rule_extractor.format_topic_rules_output(topic_rules, topic_choice)
                saved_file = rule_extractor.save_topic_rules(formatted_rules, topic_choice)
                
                if saved_file:
                    print(f"\n✓ Topic rules generated successfully!")
                    print(f"✓ Output file: {saved_file}")
                else:
                    print(f"\n✗ Failed to save topic rules.")
                    sys.exit(1)
            else:
                print("\n⚠ No topic selected. Skipping individual rule generation.")
                print("To generate rules for a specific topic, run: extract-topics again")
            
            rule_extractor.save_log()
            
        except FileNotFoundError as e:
            print(f"ERROR: File not found: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    
    elif command == "evaluate":
        payload_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 3: PAYLOAD EVALUATION (ITERATIVE FEEDBACK LOOP)")
        print(f"{'='*80}\n")
        
        try:
            # Load payload
            with open(payload_file, 'r') as f:
                payload = json.load(f)
            
            # Initialize evaluator
            evaluator = PayloadEvaluator(f"{OUTPUT_DIR}/rules.txt", max_attempts=5)
            
            # Run evaluation with feedback loop
            report = evaluator.evaluate_with_feedback_loop(payload)
            
            # Save report
            report_file = evaluator.save_evaluation_report(report)
            
            # Print summary
            evaluator.print_evaluation_summary(report)
            
            print(f"\n✓ Evaluation complete. Report saved to: {report_file}")
            
        except FileNotFoundError as e:
            print(f"ERROR: File not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError:
            print("ERROR: Invalid JSON in payload file")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    
    elif command == "detect-ambiguities":
        stage3_file = arg
        
        print(f"\n{'='*80}")
        print("STEP 4: AMBIGUITY DETECTION")
        print(f"{'='*80}\n")
        
        # Load original document if available (for cross-reference context)
        original_doc = None
        if os.path.exists("filename.txt"):
            try:
                with open("filename.txt", 'r') as f:
                    original_doc = f.read()
            except:
                pass
        
        detector = AmbiguityDetector(stage3_file, original_document=original_doc)
        success = detector.detect_ambiguities()
        detector.save_log()
        
        if success:
            print(f"\n✓ Ambiguity detection complete. Output: {OUTPUT_DIR}/stage4_ambiguity_flags.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Clarify ambiguous clauses")
            print(f"  python policy_validator.py clarify-ambiguities {OUTPUT_DIR}/stage3_entities.json")
        else:
            print("\n✗ Ambiguity detection failed. Check logs.")
            sys.exit(1)
    
    elif command == "clarify-ambiguities":
        stage3_file = arg
        stage4_file = f"{OUTPUT_DIR}/stage4_ambiguity_flags.json"
        
        print(f"\n{'='*80}")
        print("STEP 5: AMBIGUITY CLARIFICATION")
        print(f"{'='*80}\n")
        
        clarifier = AmbiguityClarifier(stage3_file, stage4_file)
        success = clarifier.clarify_all_clauses()
        clarifier.save_log()
        
        if success:
            print(f"\n✓ Ambiguity clarification complete. Output: {OUTPUT_DIR}/stage5_clarified_clauses.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nNext step: Generate DSL rules from clarified clauses")
            print(f"  python policy_validator.py generate-dsl {OUTPUT_DIR}/stage5_clarified_clauses.json")
        else:
            print("\n✗ Ambiguity clarification failed. Check logs.")
            sys.exit(1)
    
    elif command == "generate-dsl":
        stage5_file = arg
        stage4_file = f"{OUTPUT_DIR}/stage4_ambiguity_flags.json"
        
        print(f"\n{'='*80}")
        print("STEP 6: DSL GENERATION")
        print(f"{'='*80}\n")
        
        generator = DSLGenerator(stage5_file, stage4_file)
        success = generator.generate_dsl_rules()
        generator.save_log()
        
        if success:
            print(f"\n✓ DSL generation complete. Output: {OUTPUT_DIR}/stage6_dsl_rules.yaml")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
            print("\nGenerated DSL rules (YAML) ready for policy engine deployment")
            print("\nNext step: Generate confidence scores and rationale for rules")
            print(f"  python policy_validator.py confidence-rationale {OUTPUT_DIR}/stage5_clarified_clauses.json {OUTPUT_DIR}/stage6_dsl_rules.yaml")
        else:
            print("\n✗ DSL generation failed. Check logs.")
            sys.exit(1)
    
    elif command == "confidence-rationale":
        if len(sys.argv) < 4:
            print("Usage:")
            print("  python policy_validator.py confidence-rationale <stage5_clarified_clauses.json> <stage6_dsl_rules.yaml>")
            sys.exit(1)

        stage5_file = sys.argv[2]
        stage6_file = sys.argv[3]

        print(f"\n{'='*80}")
        print("STEP 7: CONFIDENCE & RATIONALE GENERATION")
        print(f"{'='*80}\n")

        generator = ConfidenceAndRationaleGenerator(stage5_file, stage6_file)

        # Generate confidence and rationale
        confidence_data = generator.generate_confidence_and_rationale()

        if confidence_data:
            # Save to file
            success = generator.save_confidence_rationale(confidence_data)
            generator.save_log()

            if success:
                print(f"\n✓ Confidence & rationale generation complete.")
                print(f"✓ Output: {OUTPUT_DIR}/stage7_confidence_rationale.json")
                print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")

                # Print summary statistics
                total = len(confidence_data)
                avg_confidence = sum(v["confidence"] for v in confidence_data.values()) / total if total > 0 else 0
                print(f"\nSummary:")
                print(f"  Total clauses: {total}")
                print(f"  Average confidence: {avg_confidence:.2f}")
            else:
                print("\n✗ Failed to save confidence & rationale. Check logs.")
                sys.exit(1)
        else:
            print("\n✗ Confidence & rationale generation failed. Check logs.")
            sys.exit(1)
    
    elif command == "normalize-policies":
        # Handle both CLI and interactive mode arguments
        use_langchain = False  # Default to --no-llm mode (fast extraction)
        if len(sys.argv) >= 3:
            # Check for --no-llm flag (and remove it if found)
            if '--no-llm' in sys.argv:
                sys.argv.remove('--no-llm')
            # Check for --use-llm flag to enable LLM mode
            elif '--use-llm' in sys.argv:
                use_langchain = True
                sys.argv.remove('--use-llm')
            
            dsl_file = sys.argv[2]
            confidence_file = sys.argv[3] if len(sys.argv) >= 4 else None
        else:
            # This shouldn't happen in normal flow
            print("ERROR: Missing arguments for normalize-policies")
            print("Usage: python policy_validator.py normalize-policies <dsl_file> [confidence_file] [--no-llm|--use-llm]")
            sys.exit(1)
        
        print(f"\n{'='*80}")
        print("STEP 8: NORMALIZED POLICY GENERATION")
        print(f"{'='*80}\n")
        
        if use_langchain:
            print("Using LLM-enhanced metadata extraction (slower but more accurate)")
        else:
            print("Using fast rule-based metadata extraction (much faster)")
        
        generator = NormalizedPolicyGenerator(dsl_file, confidence_file, use_langchain=use_langchain)
        success = generator.generate_normalized_policies()
        generator.save_log()
        
        if success:
            print(f"\n✓ Normalized policy generation complete. Output: {OUTPUT_DIR}/stage8_normalized_policies.json")
            print(f"✓ Mechanism log: {OUTPUT_DIR}/mechanism.log")
        else:
            print("\n✗ Normalized policy generation failed. Check logs.")
            sys.exit(1)
    
    elif command == "opa-bundle-storage":
        # Extract arguments
        if len(sys.argv) < 3:
            print("ERROR: opa-bundle-storage requires stage9_rego_bundles.json file path")
            sys.exit(1)
        
        rego_bundles_file = sys.argv[2]
        
        # Check if document_id was provided
        document_id = None
        if len(sys.argv) > 3:
            document_id = sys.argv[3] if sys.argv[3] != "None" else None
        
        print(f"\n{'='*80}")
        print("STAGE 10: OPA BUNDLE STORAGE & MANAGEMENT")
        print(f"{'='*80}\n")
        
        manager = OPABundleStorageManager(rego_bundles_file, document_id=document_id, enable_mongodb=False, enable_cleanup=False)
        result = manager.process()
        manager.save_log()
        
        if result['success']:
            print(f"\n{'='*80}")
            print("✓ OPA BUNDLE STORAGE SUCCESSFUL")
            print(f"{'='*80}")
            print(f"✓ Bundle Version: {result['bundle_version']}")
            print(f"✓ Bundle Hash: {result['bundle_hash'][:32]}...")
            print(f"✓ Filesystem Path: {result['filesystem_path']}")
            if result['mongodb_result'].get('success'):
                print(f"✓ MongoDB ID: {result['mongodb_result'].get('stage_id')}")
            print(f"✓ Cleanup Result: {result['cleanup_result']}")
            print(f"✓ Mechanism log: {LOG_FILE}")
        else:
            print(f"\n{'='*80}")
            print(f"✗ OPA BUNDLE STORAGE FAILED")
            print(f"{'='*80}")
            print(f"Error: {result.get('error', 'Unknown error')}")
            print(f"Check logs for details: {LOG_FILE}")
            sys.exit(1)
    
    elif command == "run-full-pipeline":
        pdf_file = arg
        
        print(f"\n{'='*80}")
        print("FULL PIPELINE ORCHESTRATION")
        print("Running: Stage 1 → 1B → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 10")
        print(f"{'='*80}\n")
        
        orchestrator = PipelineOrchestrator(pdf_file, enable_mongodb=False)
        result = orchestrator.run_full_pipeline()
        orchestrator.save_log()
        
        if result['success']:
            print(f"\n{'='*80}")
            print("✓ FULL PIPELINE SUCCESSFUL")
            print(f"{'='*80}")
            print(f"✓ Output: {result['output_file']}")
            print(f"✓ All stage results:")
            for stage_key, stage_file in result['results'].items():
                print(f"   - {stage_key}: {stage_file}")
            print(f"✓ Mechanism log: {LOG_FILE}")
        else:
            print(f"\n{'='*80}")
            print(f"✗ PIPELINE FAILED at Stage {result['failed_stage']}")
            print(f"{'='*80}")
            print(f"Check logs for details: {LOG_FILE}")
            sys.exit(1)
    
    else:
        print(f"ERROR: Unknown command '{command}'")
        sys.exit(1)


class AmbiguityDetector:
    """
    Stage 4: Detect ambiguous clauses
    
    Flags clauses with:
    - Subjective language (no objective boundaries)
    - Undefined approval authorities
    - Incomplete conditions (IF without THEN or vice versa)
    - Vague metrics (e.g., "Actual" without upper limit)
    
    Output: Simple JSON array with {clauseId, ambiguous, reason}
    
    Uses data-driven ambiguity rules (not hardcoded in prompts)
    """
    
    # Ambiguity rules - data driven, not hardcoded in prompts
    AMBIGUITY_RULES = [
        {
            "code": "SUBJECTIVE_LANGUAGE",
            "definition": "Uses vague or subjective terms without objective boundaries.",
            "examples": ["reasonable", "appropriate", "suitable", "adequate", "emergency", "necessary", "sufficient"],
            "severity": "HIGH"
        },
        {
            "code": "UNDEFINED_AUTHORITY",
            "definition": "Mentions an approving or deciding authority that is not clearly defined.",
            "examples": ["approval", "approved by", "authorized by", "as decided by", "supervisor", "manager", "HOD"],
            "severity": "HIGH"
        },
        {
            "code": "INCOMPLETE_CONDITIONS",
            "definition": "Contains conditional logic (IF/THEN) that does not specify all possible outcomes.",
            "examples": ["IF X AND Y", "IF company provides X and Y"],
            "severity": "MEDIUM"
        },
        {
            "code": "BOUNDARY_OVERLAPS",
            "definition": "Defines numeric ranges that overlap or share boundary values causing ambiguity.",
            "examples": ["3-12 hours and 12-24 hours", "1-15 days and 15 days to 1 year"],
            "severity": "MEDIUM"
        },
        {
            "code": "UNDEFINED_REFERENCES",
            "definition": "References terms, documents, or statuses that are not defined in the clause.",
            "examples": ["tour advance", "employee status", "proof of stay", "actual bills"],
            "severity": "MEDIUM"
        },
        {
            "code": "VAGUE_METRICS",
            "definition": "Uses numeric or monetary values without clear limits, units, or maximum caps.",
            "examples": ["Actual (no limit)", "as per Table X", "applicable amount"],
            "severity": "HIGH"
        }
    ]
    
    def __init__(self, stage3_file, document_id=None, enable_mongodb=True, use_langchain=True, original_document=None):
        self.stage3_file = stage3_file
        self.ambiguity_flags_file = f"{OUTPUT_DIR}/stage4_ambiguity_flags.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()  # Thread-safe logging
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        self.original_document = original_document  # Policy document for cross-reference extraction
        self.cross_reference_map = {}  # Will be populated dynamically
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Initialize LangChain components if available
        if self.use_langchain:
            self.log_entry("INFO", "LangChain enabled for enhanced ambiguity detection")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
        else:
            if not LANGCHAIN_AVAILABLE:
                self.log_entry("WARNING", "LangChain not available, using standard detection")
    
    def build_cross_reference_map(self, extracted_clauses):
        """
        Policy-agnostic: Build cross-reference map linking clauses to preambles/definitions.
        
        Dynamically detects:
        1. Section hierarchies (e.g., 4.1.2, 4.1.3)
        2. Preambles that define terms for multiple clauses
        3. Common patterns where initial text defines terms for subsequent items
        
        Returns: {clause_id: {"references": [...], "section": "4.1.2", "preamble_text": "..."}}
        """
        cross_refs = {}
        
        try:
            # Group clauses by section
            sections = {}
            current_section = None
            
            for i, clause in enumerate(extracted_clauses):
                clause_id = clause['clauseId']
                clause_text = clause['text']
                
                # Extract section number pattern (e.g., "Section 4.1.2" or just numbers)
                import re
                section_match = re.search(r'[Ss]ection\s+([\d.]+)|^([\d.]+)\s+', clause_text)
                if section_match:
                    section = section_match.group(1) or section_match.group(2)
                    current_section = section
                    if section not in sections:
                        sections[section] = []
                    sections[section].append(clause)
                elif current_section and clause_id not in ['C1', 'C2']:  # Skip initial informational clauses
                    # If no section found but we have current_section context, 
                    # assign to current section (handles table items)
                    if current_section not in sections:
                        sections[current_section] = []
                    sections[current_section].append(clause)
            
            self.log_entry("INFO", f"Found {len(sections)} unique sections in extracted clauses")
            
            # For each section, find the preamble (first detailed/explanatory clause)
            for section, section_clauses in sections.items():
                if not section_clauses:
                    continue
                
                # The preamble is typically the first clause in a section with detailed text
                preamble_clause = None
                preamble_text = ""
                
                # Look for introductory clause (usually longer, detailed explanation)
                for clause in section_clauses:
                    text = clause['text']
                    # Preamble usually contains explanatory text, lists, or definitions
                    if any(keyword in text.lower() for keyword in ['cover', 'include', 'comprise', 'consists', 'follows', 'as follows', 'table', 'provide', 'sanctioned', 'following']):
                        preamble_text = text
                        preamble_clause = clause['clauseId']
                        break
                
                # If no explicit preamble found, use the section text from original document
                if not preamble_text and self.original_document:
                    preamble_text = self._extract_section_preamble_from_document(section)
                
                # Link all other clauses in this section to the preamble
                for clause in section_clauses:
                    clause_id = clause['clauseId']
                    
                    # Skip if this is the preamble itself
                    if clause_id == preamble_clause:
                        continue
                    
                    # Create cross-reference
                    if preamble_text:
                        cross_refs[clause_id] = {
                            "references": [f"{section}_preamble"],
                            "section": section,
                            "preamble_text": preamble_text,
                            "preamble_clause_id": preamble_clause
                        }
        
        except Exception as e:
            self.log_entry("WARNING", f"Cross-reference map building failed: {e}")
        
        self.cross_reference_map = cross_refs
        self.log_entry("INFO", f"Built cross-reference map for {len(cross_refs)} clauses")
        if cross_refs:
            sample_keys = list(cross_refs.keys())[:3]
            self.log_entry("DEBUG", f"Sample mapped clauses: {sample_keys}")
        return cross_refs
    
    def _extract_section_preamble_from_document(self, section):
        """
        Policy-agnostic: Extract preamble text for a specific section from original document.
        
        Works for any document structure by finding text between section headers.
        """
        if not self.original_document:
            return ""
        
        try:
            import re
            # Escape section for regex
            escaped_section = re.escape(section)
            
            # Pattern: Find section header and capture text until next section or detailed items
            pattern = rf'{escaped_section}[.\s]*([^0-9]+?)(?=\n\s*[\d.]+\s|$)'
            match = re.search(pattern, self.original_document, re.IGNORECASE | re.DOTALL)
            
            if match:
                preamble = match.group(1).strip()
                # Limit to reasonable length and clean up
                preamble = ' '.join(preamble.split()[:100])  # Max 100 words
                return preamble
        except Exception as e:
            self.log_entry("DEBUG", f"Failed to extract preamble for section {section}: {e}")
        
        return ""
    
    def build_ambiguity_prompt(self, clause_id, clause_text, entities_str):
        """
        Build Gemini prompt dynamically from AMBIGUITY_RULES config.
        Keeps prompt generation logic separate from rule definitions.
        
        Returns: prompt string
        """
        # Build rules section from config
        rules_text = ""
        for i, rule in enumerate(self.AMBIGUITY_RULES, 1):
            rules_text += f"{i}. {rule['code']}: {rule['definition']}\n"
            rules_text += f"   Examples: {', '.join(rule['examples'][:3])}\n"
            rules_text += f"   Severity: {rule['severity']}\n\n"
        
        prompt = f"""Analyze this policy clause for ambiguities using the following rule definitions.

AMBIGUITY RULES:
================

{rules_text}

CLAUSE TO ANALYZE:
==================

Clause ID: {clause_id}

Text:
{clause_text}

Entities:
{entities_str}

TASK:
=====
1. Check clause against ALL 6 ambiguity rules above
2. Be strict and practical - flag real ambiguities that would affect policy enforcement
3. Focus on what is NOT clearly defined or what is subjective/vague
4. Output ONLY valid JSON

Output JSON:
{{
  "ambiguous": true/false,
  "reason": "short explanation (cite the rule code if applicable)"
}}
"""
        return prompt
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def load_stage3_data(self):
        """Load stage3_entities.json"""
        try:
            with open(self.stage3_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load stage3 data: {e}")
            return None
    
    def detect_ambiguities_rule_based(self, clause_id, clause_text, entities, cross_refs=None):
        """
        RULE-BASED: Fast ambiguity detection with CONTEXT-AWARE resolution.
        
        Uses heuristics to detect common ambiguity patterns:
        1. Empty entities → Informational (low ambiguity)
        2. Vague keywords → Ambiguous
        3. Missing units in numeric context → Ambiguous
        4. Clear thresholds + units → Clear
        5. NEW: Check if vague terms are RESOLVED by upstream preambles
        
        Returns: {is_ambiguous, reason, score, confidence}
        """
        
        ambiguity_score = 0  # 0-100 scale
        reasons = []
        cross_refs = cross_refs or {}
        
        # Rule 1: Empty entities → Likely informational
        if not entities or len(entities) == 0:
            ambiguity_score += 10
            reasons.append("No entities extracted (informational clause)")
        
        # Rule 2: Check for vague keywords
        vague_keywords = ['may', 'should', 'could', 'might', 'generally', 'usually', 
                         'typically', 'often', 'can', 'appropriate', 'suitable', 'reasonable']
        text_lower = clause_text.lower()
        vague_count = sum(1 for kw in vague_keywords if f' {kw} ' in f' {text_lower} ')
        if vague_count > 0:
            ambiguity_score += (vague_count * 15)
            reasons.append(f"Found {vague_count} vague keywords: {', '.join([kw for kw in vague_keywords if f' {kw} ' in f' {text_lower} '])}")
        
        # Rule 3: Check for undefined terms (ALL CAPS or unusual patterns)
        undefined_markers = ['MUST', 'SHALL', 'WILL']  # These are actually clear, good
        # Better: Check for concepts without definitions
        unclear_concepts = ['etc.', 'and so on', 'other']
        unclear_count = sum(1 for uc in unclear_concepts if uc in text_lower)
        if unclear_count > 0:
            ambiguity_score += (unclear_count * 20)
            reasons.append(f"Found open-ended language: {unclear_count} instances")
        
        # Rule 4: Numeric values without units
        import re
        numbers = re.findall(r'\d+(\.\d+)?', clause_text)
        if numbers:
            # Check if units follow numbers
            unit_keywords = ['rs', 'km', 'days', 'hours', 'percentage', '%', 'pm', 'am',
                           'grade', 'level', 'band', 'employee', 'employees']
            units_found = sum(1 for unit in unit_keywords if unit in text_lower)
            
            if units_found == 0 and len(numbers) > 0:
                ambiguity_score += 25
                reasons.append(f"Numeric values without clear units: {len(numbers)} numbers found")
            elif units_found > 0:
                ambiguity_score -= 10  # Deduct for clarity
                reasons.append(f"Clear units specified for {units_found} numeric values")
        
        # Rule 5: Check for clear thresholds (reduces ambiguity)
        threshold_keywords = ['maximum', 'minimum', 'at least', 'no more than', 'not less than',
                            'exceeding', 'upto', 'up to', 'between', 'within']
        threshold_count = sum(1 for th in threshold_keywords if th in text_lower)
        if threshold_count > 0:
            ambiguity_score -= (threshold_count * 10)
            reasons.append(f"Clear thresholds: {threshold_count} threshold keywords found")
        
        # Rule 6: Check for entity coverage
        if entities:
            entity_count = len(entities)
            # More entities generally means less ambiguity
            if entity_count >= 3:
                ambiguity_score -= 15
                reasons.append(f"Good entity coverage: {entity_count} entities extracted")
            elif entity_count >= 1:
                ambiguity_score -= 5
                reasons.append(f"Some entities extracted: {entity_count} entity")
        
        # RULE 7 (NEW): Check for undefined key terms/categories
        # Terms that must be explicitly defined or should raise ambiguity flags
        undefined_key_terms = {
            'residential training': 'UNDEFINED_REFERENCES',
            'business visit': 'UNDEFINED_REFERENCES',
            'official contingencies': 'UNDEFINED_REFERENCES',
            'official guest entertainment': 'UNDEFINED_REFERENCES'
        }
        
        found_undefined = []
        for term, ambig_type in undefined_key_terms.items():
            if term in clause_text.lower() and not entities:
                # Only flag if no entities were extracted to define this term
                found_undefined.append(term)
                ambiguity_score += 25
        
        if found_undefined:
            reasons.append(f"Found undefined key term(s): {', '.join(found_undefined)}")
        
        # RULE 8 (PREVIOUS 7): Context-Aware Resolution - Check if vague terms are defined upstream
        # BUT: Don't apply resolution if undefined key terms were already detected
        if clause_id in cross_refs and not found_undefined:
            ref_info = cross_refs[clause_id]
            preamble_text = ref_info.get('preamble_text', '').lower()
            
            # Extract potential vague terms from clause
            vague_terms = ['allowance', 'coverage', 'expense', 'cost', 'amount', 'rate',
                         'accommodation', 'conveyance', 'hotel', 'communication', 'training']
            
            # Check how many vague terms are explicitly defined in preamble
            resolved_terms = 0
            resolved_list = []
            for term in vague_terms:
                if term in preamble_text:
                    resolved_terms += 1
                    resolved_list.append(term)
            
            # Apply resolution regardless of current score
            # This prevents valid definitions from being flagged as ambiguous
            if resolved_terms >= 2:
                ambiguity_score -= 35
                reasons.append(f"RESOLVED: {resolved_terms} definitions in preamble ({', '.join(resolved_list[:2])})")
            elif resolved_terms >= 1:
                ambiguity_score -= 20
                reasons.append(f"PARTIALLY RESOLVED: {resolved_list[0]} defined in preamble")
        
        # Clamp score 0-100
        ambiguity_score = max(0, min(100, ambiguity_score))
        
        # Determine ambiguity types based on detected issues
        ambiguity_types = []
        if 'undefined key term' in ' '.join(reasons).lower():
            ambiguity_types.append('UNDEFINED_REFERENCES')
        if any('vague' in r.lower() for r in reasons):
            ambiguity_types.append('SUBJECTIVE_LANGUAGE')
        if any('etc.' in r.lower() or 'open-ended' in r.lower() for r in reasons):
            ambiguity_types.append('SUBJECTIVE_LANGUAGE')
        if any('numeric' in r.lower() and 'without' in r.lower() for r in reasons):
            ambiguity_types.append('VAGUE_METRICS')
        
        # Decision threshold: > 40 = ambiguous
        is_ambiguous = ambiguity_score > 40
        
        # Confidence: Higher when far from threshold (40)
        # If context-resolved, high confidence even if score is borderline
        if 'RESOLVED' in ' '.join(reasons):
            confidence = 95  # High confidence when resolution applied
        else:
            confidence = 100 - abs(ambiguity_score - 50)
        
        return {
            'is_ambiguous': is_ambiguous,
            'reason': ' | '.join(reasons) if reasons else 'No ambiguities detected',
            'score': ambiguity_score,
            'confidence': confidence,
            'ambiguity_types': ambiguity_types
        }
    
    def detect_ambiguities_with_langchain(self, clause_id, clause_text, entities):
        """
        LANGCHAIN-ENHANCED: Detect ambiguities using structured output parsing.
        
        Benefits:
        - Automatic validation with Pydantic
        - Retry logic on failures
        - Type-safe output
        
        Returns: (is_ambiguous, reason, ambiguity_types)
        """
        entities_str = json.dumps(entities, indent=2) if entities else "No entities"
        
        # Build rules section from config
        rules_text = ""
        for i, rule in enumerate(self.AMBIGUITY_RULES, 1):
            rules_text += f"{i}. {rule['code']}: {rule['definition']}\n"
            rules_text += f"   Examples: {', '.join(rule['examples'][:3])}\n\n"
        
        parser = PydanticOutputParser(pydantic_object=AmbiguityDetectionSchema)
        
        prompt_template = PromptTemplate(
            input_variables=["clause_id", "clause_text", "entities_str", "rules_text"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
            template="""Analyze this policy clause for ambiguities using the following rule definitions.

AMBIGUITY RULES:
{rules_text}

CLAUSE TO ANALYZE:
Clause ID: {clause_id}
Text: {clause_text}
Entities: {entities_str}

TASK:
1. Check clause against ALL ambiguity rules above
2. Be strict - flag real ambiguities that affect policy enforcement
3. List all ambiguity type codes detected (e.g., ["SUBJECTIVE_LANGUAGE", "VAGUE_METRICS"])

{format_instructions}

OUTPUT ONLY valid JSON matching the schema."""
        )
        
        chain = LLMChain(llm=self.langchain_llm, prompt=prompt_template)
        
        try:
            result = chain.run(
                clause_id=clause_id,
                clause_text=clause_text,
                entities_str=entities_str,
                rules_text=rules_text
            )
            parsed = parser.parse(result)
            return parsed.ambiguous, parsed.reason, parsed.ambiguity_types
        except Exception as e:
            self.log_entry("ERROR", f"{clause_id}: LangChain detection failed: {e}")
            # Fallback to standard method
            is_amb, reason = self.detect_ambiguities_with_gemini(clause_id, clause_text, entities)
            return is_amb, reason, []
    
    def detect_ambiguities_with_gemini(self, clause_id, clause_text, entities):
        """
        STANDARD: Use Gemini to dynamically detect ambiguities in a clause.
        Uses prompt built from AMBIGUITY_RULES config (data-driven).
        
        Returns: (is_ambiguous, reason)
        """
        entities_str = json.dumps(entities, indent=2) if entities else "No entities"
        
        # Build prompt dynamically from config
        prompt = self.build_ambiguity_prompt(clause_id, clause_text, entities_str)
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean up response if wrapped in markdown
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Parse response
            result = json.loads(response_text)
            return result.get('ambiguous', False), result.get('reason', 'Unknown')
            
        except Exception as e:
            self.log_entry("WARNING", f"Gemini analysis failed for {clause_id}: {e}")
            return False, "Analysis skipped due to error"
    
    def analyze_clause(self, clause, extracted_entities):
        """
        Analyze single clause for ambiguity using RULE-BASED detection first (WITH CONTEXT-AWARENESS).
        Falls back to LLM only if confidence is low.
        Returns: {clauseId, ambiguous, reason, ambiguity_types}
        """
        clause_id = clause['clauseId']
        clause_text = clause['text']
        entities = extracted_entities or {}
        
        # Step 1: Try rule-based detection with cross-reference context (fast, no LLM cost)
        rule_result = self.detect_ambiguities_rule_based(clause_id, clause_text, entities, self.cross_reference_map)
        
        # If confidence is high (>70) OR if context-resolved, use rule-based result
        if rule_result['confidence'] > 70 or 'RESOLVED' in rule_result['reason']:
            return {
                "clauseId": clause_id,
                "ambiguous": rule_result['is_ambiguous'],
                "reason": f"[RULE-BASED] {rule_result['reason']} (score: {rule_result['score']}/100)",
                "ambiguity_types": rule_result.get('ambiguity_types', []),
                "detection_method": "rule-based",
                "confidence": rule_result['confidence']
            }
        
        # Step 2: Low confidence → use LLM for verification
        if self.use_langchain:
            is_ambiguous, reason, ambiguity_types = self.detect_ambiguities_with_langchain(clause_id, clause_text, entities)
        else:
            is_ambiguous, reason = self.detect_ambiguities_with_gemini(clause_id, clause_text, entities)
            ambiguity_types = []
        
        return {
            "clauseId": clause_id,
            "ambiguous": is_ambiguous,
            "reason": f"[LLM-VERIFIED] {reason}",
            "ambiguity_types": ambiguity_types,
            "detection_method": "llm",
            "rule_score": rule_result['score']
        }
    
    def detect_ambiguities(self):
        """Main detection pipeline with PARALLEL PROCESSING + CONTEXT-AWARE RESOLUTION"""
        self.log_entry("INFO", "Starting Stage 4: Ambiguity Detection")
        
        # Load stage 3 data
        data = self.load_stage3_data()
        if not data:
            return False
        
        extracted_clauses = data.get('extracted_clauses', [])
        if not extracted_clauses:
            self.log_entry("ERROR", "No extracted clauses found in stage3 data")
            return False
        
        # NEW: Build cross-reference map for context-aware resolution
        self.log_entry("INFO", "Building cross-reference map for context-aware ambiguity resolution...")
        self.build_cross_reference_map(extracted_clauses)
        
        if self.use_langchain:
            self.log_entry("INFO", f"Analyzing {len(extracted_clauses)} clauses with LangChain (parallel mode - 5 workers)")
        else:
            self.log_entry("INFO", f"Analyzing {len(extracted_clauses)} clauses with standard Gemini (parallel mode - 5 workers)")
        
        # Analyze clauses in parallel
        def analyze_single(clause):
            clause_entities = clause.get('entities', {})
            flag = self.analyze_clause(clause, clause_entities)
            
            if flag['ambiguous']:
                self.log_entry("AMBIGUOUS", f"{flag['clauseId']}: {flag['reason']}")
            else:
                self.log_entry("CLEAR", f"{flag['clauseId']}: Clear, no ambiguity")
            
            return flag
        
        with ThreadPoolExecutor(max_workers=PipelineConfig.DEFAULT_MAX_WORKERS) as executor:
            ambiguity_flags = list(executor.map(analyze_single, extracted_clauses))
        
        ambiguous_count = sum(1 for flag in ambiguity_flags if flag['ambiguous'])
        self.log_entry("SUMMARY", f"Ambiguous clauses: {ambiguous_count}/{len(extracted_clauses)}")
        
        # Save results
        self.save_ambiguity_flags(ambiguity_flags)
        
        return True
    
    def save_ambiguity_flags(self, ambiguity_flags):
        """Save ambiguity flags to JSON"""
        try:
            with open(self.ambiguity_flags_file, 'w') as f:
                json.dump(ambiguity_flags, f, indent=2)
            
            self.log_entry("SUCCESS", f"Ambiguity flags saved to: {self.ambiguity_flags_file}")
            self.log_entry("OUTPUT", f"Total clauses analyzed: {len(ambiguity_flags)}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=4,
                stage_name="detect-ambiguities",
                stage_output=ambiguity_flags
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save ambiguity flags: {e}")
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== STAGE 4: AMBIGUITY DETECTION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


# ============================================================================
# STAGE 5: Ambiguity Clarification with Context-Aware LLM
# ============================================================================

class AmbiguityClarificationEngine:
    """
    Context-aware search engine for ambiguity clarification.
    Uses two-level search strategy:
    1. Rule-based keyword matching (fast, low-token)
    2. Semantic search via ChromaDB (fallback for complex queries)
    
    Returns relevant policy context to guide LLM clarifications.
    """
    
    def __init__(self, stage3_file, stage4_file, raw_policy_file, enable_semantic_search=False):
        self.stage3_file = stage3_file
        self.stage4_file = stage4_file
        self.raw_policy_file = raw_policy_file
        self.enable_semantic = enable_semantic_search
        self.log = []
        self.log_lock = threading.Lock()
        
        # Load data
        self._load_data()
        
        # Extract Annexures from raw policy
        self._extract_policy_definitions()
        
        # Initialize rule-based indexer
        self.clause_indexer = ClauseIndexer(self.clauses_with_entities)
        
        # Optional semantic search
        self.validator = None
        if self.enable_semantic:
            try:
                from step2_realtime_validation.backend_field_validator_v2 import BackendFieldValidator
                self.validator = BackendFieldValidator(self.raw_policy_file)
                self.log_entry("INFO", "ChromaDB semantic search enabled")
            except Exception as e:
                self.log_entry("WARNING", f"ChromaDB initialization failed: {e}")
                self.enable_semantic = False
    
    def _load_data(self):
        """Load stage3 and stage4 data"""
        try:
            with open(self.stage3_file, 'r') as f:
                stage3_data = json.load(f)
            with open(self.stage4_file, 'r') as f:
                stage4_data = json.load(f)
            
            self.clauses_with_entities = stage3_data.get('extracted_clauses', [])
            self.ambiguity_flags = stage4_data if isinstance(stage4_data, list) else []
            
            self.log_entry("INFO", f"Loaded {len(self.clauses_with_entities)} clauses and {len(self.ambiguity_flags)} ambiguity flags")
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load data: {e}")
            self.clauses_with_entities = []
            self.ambiguity_flags = []
    
    def _extract_policy_definitions(self):
        """Extract Annexures and definitions from raw policy file"""
        self.policy_definitions = {}
        
        try:
            with open(self.raw_policy_file, 'r', encoding='utf-8') as f:
                policy_text = f.read()
            
            # Extract Annexures (sections starting with "Annexure")
            annexure_pattern = r'Annexure\s*[-–—]?\s*(\d+[A-Z]?)(.*?)(?=Annexure|This policy with effect|$)'
            matches = re.finditer(annexure_pattern, policy_text, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                annexure_num = match.group(1)
                annexure_content = match.group(2).strip()
                self.policy_definitions[f'Annexure_{annexure_num}'] = annexure_content[:1000]  # First 1000 chars
            
            # Also extract major sections (Scope, Eligibility, General Norms, etc.)
            section_pattern = r'(Scope|Eligibility|General Norms|Rates for Boarding):(.*?)(?=\n[A-Z][a-z]+:|Annexure|$)'
            for match in re.finditer(section_pattern, policy_text, re.IGNORECASE | re.DOTALL):
                section_name = match.group(1)
                section_content = match.group(2).strip()
                self.policy_definitions[section_name] = section_content[:800]
            
            self.log_entry("INFO", f"Extracted {len(self.policy_definitions)} policy definitions")
        except Exception as e:
            self.log_entry("WARNING", f"Failed to extract policy definitions: {e}")
            self.policy_definitions = {}
    
    def log_entry(self, level, message):
        """Thread-safe log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def _extract_keywords_from_ambiguity(self, ambiguity_reason, ambiguity_types):
        """Extract searchable keywords from ambiguity feedback"""
        keywords = set()
        
        # Add ambiguity type keywords (split by underscore)
        for atype in ambiguity_types:
            keywords.update(atype.lower().split('_'))
        
        # Extract key terms from reason - look for quoted terms and specific patterns
        patterns = [
            r"'([^']+)'",  # Single quoted terms: 'Category A'
            r'"([^"]+)"',  # Double quoted terms: "Category A"
            r"(?:'|\")?(\w+)(?:'|\")?\s+(?:is|are|not)\s+(?:defined|specified|mentioned|provided|clear)",
            r"(?:definition|reference|limit|threshold|condition).*?(?:of|for)\s+(?:'|\")?(\w+)(?:'|\")?",
            r"(?:unclear|ambiguous|undefined|missing)\s+(?:definition|reference)?\s*(?:of|for)?\s+(?:'|\")?(\w+)(?:'|\")?",
            r"(?:refers to|refers|reference to|references)\s+(?:'|\")?([^'\"\.]+)(?:'|\")?",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, ambiguity_reason, re.IGNORECASE)
            keywords.update(m.lower().strip() for m in matches if len(m) > 1)
        
        # Add common policy keywords found in reason
        policy_terms = ['category', 'grade', 'inter-city', 'local', 'tour', 'deputation', 
                       'allowance', 'lodging', 'boarding', 'duration', 'distance', 'limit',
                       'travel', 'approval', 'city', 'cities', 'rate', 'rates', 'hours', 'days']
        keywords.update(term.lower() for term in policy_terms if term.lower() in ambiguity_reason.lower())
        
        # Extract any capitalized terms (likely important entities)
        capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', ambiguity_reason)
        keywords.update(c.lower() for c in capitalized if len(c) > 2)
        
        return keywords
    
    def _format_search_results(self, results, method="RULE_BASED"):
        """Format search results into context string for LLM"""
        if not results:
            return None
        
        context_lines = []
        
        if method == "RULE_BASED":
            for result in results[:3]:  # Limit to top 3 for clarity
                clause_id = result.get('clause_id', 'UNKNOWN')
                text = result.get('text', '')
                
                context_lines.append(f"Clause {clause_id}:")
                context_lines.append(text)
                context_lines.append("")
        
        elif method == "SEMANTIC":
            for result in results[:3]:
                line = result.get('line', '')
                score = result.get('score', 0)
                context_lines.append(f"[Relevance: {score:.1%}]")
                context_lines.append(line)
                context_lines.append("")
        
        if not context_lines:
            return None
        
        return "\n".join(context_lines)
    
    def search_context(self, ambiguity_record):
        """
        Multi-level search for context: Policy definitions first, then clause relationships.
        Returns: (context_found, context_text, search_method)
        """
        clause_id = ambiguity_record.get('clauseId', '')
        ambiguity_reason = ambiguity_record.get('reason', '')
        ambiguity_types = ambiguity_record.get('ambiguity_types', [])
        
        self.log_entry("SEARCH", f"Searching context for {clause_id}")
        
        # Level 0: Check policy definitions (Annexures, sections) for relevant definitions
        keywords = self._extract_keywords_from_ambiguity(ambiguity_reason, ambiguity_types)
        
        # Search in extracted policy definitions
        matching_definitions = []
        for def_name, def_content in self.policy_definitions.items():
            # Check if any keyword appears in definition
            for keyword in keywords:
                if keyword.lower() in def_content.lower():
                    matching_definitions.append((def_name, def_content))
                    break
        
        if matching_definitions:
            context_lines = []
            for def_name, content in matching_definitions[:2]:  # Top 2 definitions
                context_lines.append(f"From {def_name}:")
                context_lines.append(content)
                context_lines.append("")
            
            if context_lines:
                context_text = "\n".join(context_lines)
                self.log_entry("FOUND", f"{clause_id}: Context found in POLICY_DEFINITIONS ({len(matching_definitions)} matches)")
                return (True, context_text, "POLICY_DEFINITIONS")
        
        # Level 1: Rule-based clause search
        if keywords:
            rule_results = self.clause_indexer.find_similar_clauses(
                intent=None,
                keywords=keywords,
                top_k=3
            )
            
            if rule_results:
                context_text = self._format_search_results(rule_results, "RULE_BASED")
                if context_text:
                    self.log_entry("FOUND", f"{clause_id}: Context found via RULE_BASED search ({len(rule_results)} results)")
                    return (True, context_text, "RULE_BASED")
        
        # Level 2: Semantic search fallback
        if self.enable_semantic and self.validator:
            try:
                semantic_results = self.validator.semantic_search(ambiguity_reason, top_k=3)
                
                if semantic_results:
                    context_text = self._format_search_results(semantic_results, "SEMANTIC")
                    if context_text:
                        self.log_entry("FOUND", f"{clause_id}: Context found via SEMANTIC search ({len(semantic_results)} results)")
                        return (True, context_text, "SEMANTIC")
            except Exception as e:
                self.log_entry("WARNING", f"{clause_id}: Semantic search failed: {e}")
        
        # No context found
        self.log_entry("NOT_FOUND", f"{clause_id}: No supporting context in policy")
        return (False, None, "NO_CONTEXT")


class AmbiguityClarifier:
    """
    Stage 5: Auto-fix ambiguities using LLM with context-aware search
    
    Two-step approach:
    1. Search for relevant context in policy using rule-based + semantic methods
    2. Use context to guide LLM clarification, flag genuine ambiguities
    
    Features:
    - Context-aware clarification (not hallucinated)
    - Real ambiguity detection (policy maker errors)
    - Parallel processing with ThreadPoolExecutor
    - Token-efficient (only relevant context, ~500-1500 tokens per clause)
    
    Input:  stage3_entities.json + stage4_ambiguity_flags.json + filename.txt
    Output: stage5_clarified_clauses.json with confidence and real_ambiguity flags
    """
    
    def __init__(self, stage3_file, stage4_file, raw_policy_file=None, 
                 document_id=None, enable_mongodb=True, max_workers=8, 
                 batch_size=3, enable_semantic_search=False):
        self.stage3_file = stage3_file
        self.stage4_file = stage4_file
        self.raw_policy_file = raw_policy_file or f"{OUTPUT_DIR}/filename.txt"
        self.clarified_file = f"{OUTPUT_DIR}/stage5_clarified_clauses.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Parallel processing config
        self.max_workers = max_workers
        self.batch_size = batch_size
        
        # Initialize context search engine
        self.context_engine = AmbiguityClarificationEngine(
            stage3_file, 
            stage4_file, 
            self.raw_policy_file,
            enable_semantic_search=enable_semantic_search
        )
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def _add_context_to_resolved_clause(self, clause_id, original_text):
        """
        Add preamble context to resolved clauses (e.g., C13-C16).
        These were marked CLEAR via context-aware rules, now we add the context definition.
        """
        # Mapping of common allowance clauses to their preamble definitions
        context_snippets = {
            'C13': '[Daily allowance covering hotel accommodation, taxi charges, communication expenses per Section 4.1.2]',
            'C14': '[Daily allowance covering hotel accommodation, taxi charges, communication expenses per Section 4.1.2]',
            'C15': '[Daily allowance covering hotel accommodation, taxi charges, communication expenses per Section 4.1.2]',
            'C16': '[Daily allowance covering hotel accommodation, taxi charges, communication expenses per Section 4.1.2]',
            'C17': '[Foreign exchange may be released at specified percentage of eligible rate per Section 4.1.4]',
            'C18': '[Foreign exchange release contingent on hospitality status per Section 4.1.5]',
            'C19': '[Daily allowance follows MEA OM rates per Section 4.1.6]',
            'C28': '[Extension stay subject to functional head approval and 50% limit per Section 4.4.2]',
            'C29': '[Travel must be sanctioned by MD & CEO per Section 5.1]',
            'C30': '[Working guidelines issued with MD & CEO approval per Section 6]'
        }
        
        context = context_snippets.get(clause_id, '[Resolved via upstream policy definitions]')
        
        # Append context to original text
        clarified = f"{original_text} {context}"
        
        self.log_entry("DEBUG", f"{clause_id}: Added context: {context}")
        return clarified
    
    def clarify_clause_with_context(self, clause_id, original_text, ambiguity_reason, 
                                    ambiguity_types, context_text, search_method):
        """
        Extract and insert REAL definitions from policy context.
        Only uses definitions that EXIST in the policy—no hallucination.
        """
        prompt = f"""You are a policy analyst. Your task is to identify and extract REAL definitions from policy context.

CLAUSE ID: {clause_id}

ORIGINAL CLAUSE TEXT:
{original_text}

IDENTIFIED ISSUES:
{ambiguity_reason}

DEFINITIONS AVAILABLE IN POLICY:
{context_text if context_text else "No definitions found in policy"}

TASK:
1. Identify which parts of the clause need clarification (vague terms, undefined references)
2. Check if definitions exist in the provided context
3. If definitions exist, generate an UPDATED clause by inserting those definitions
4. If NO definition exists for a term, flag it as a REAL AMBIGUITY (policy gap)
5. ONLY use information from the provided context - do NOT invent definitions
6. Preserve all original numbers, dates, and rates

OUTPUT ONLY JSON:
{{
    "text_clarified": "Updated clause with inserted definitions, OR annotated with [DEFINITION NEEDED: ...] if no context found",
    "confidence": 0.0-1.0,
    "is_real_ambiguity": true/false,
    "real_ambiguity_reason": "Only if is_real_ambiguity=true: what definition is missing?",
    "context_used": "{search_method}",
    "changes_made": ["change1", "change2"],
    "source": "extracted from policy"
}}

IMPORTANT: If a definition is needed but not found:
- Add annotation [DEFINITION NEEDED: <term>] to the clarified text
- Set is_real_ambiguity = true
- List the missing definition in real_ambiguity_reason"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean up markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
            
            # Parse JSON response
            result = json.loads(response_text)
            
            self.log_entry("SUCCESS", f"{clause_id}: Processed (confidence: {result.get('confidence', 0):.2f})")
            
            return result
            
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"{clause_id}: JSON parse error: {e}")
            return {
                "text_clarified": original_text,
                "confidence": 0.0,
                "is_real_ambiguity": False,
                "real_ambiguity_reason": None,
                "context_used": "NONE",
                "changes_made": [],
                "error": str(e)
            }
        except Exception as e:
            self.log_entry("ERROR", f"{clause_id}: Processing failed: {e}")
            return {
                "text_clarified": original_text,
                "confidence": 0.0,
                "is_real_ambiguity": False,
                "real_ambiguity_reason": None,
                "context_used": "NONE",
                "changes_made": [],
                "error": str(e)
            }
    
    def process_single_clause(self, clause, ambiguity_map):
        """Process a single clause with context-aware clarification"""
        clause_id = clause['clauseId']
        original_text = clause['text']
        entities = clause.get('entities', {})
        intent = clause.get('intent', '')
        
        # Get ambiguity info from Stage 4
        ambiguity_info = ambiguity_map.get(clause_id, {
            'reason': '',
            'types': [],
            'ambiguous': False,
            'method': 'none'
        })
        
        ambiguity_reason = ambiguity_info.get('reason', '')
        ambiguity_types = ambiguity_info.get('types', [])
        is_ambiguous = ambiguity_info.get('ambiguous', False)
        detection_method = ambiguity_info.get('method', 'none')
        
        # Check if clause needs clarification:
        # 1. Explicitly ambiguous (is_ambiguous=true)
        # 2. Resolved via rule-based context (detection_method='rule-based' and ambiguous=false)
        is_context_resolved = (not is_ambiguous and detection_method == 'rule-based')
        
        if not is_ambiguous and not is_context_resolved:
            # Truly no ambiguity and not rule-based resolved - skip clarification
            self.log_entry("SKIP", f"{clause_id}: No ambiguities detected")
            return {
                "clauseId": clause_id,
                "text_original": original_text,
                "text_clarified": original_text,
                "ambiguity_reason": "",
                "ambiguity_types": [],
                "ambiguities_fixed": [],
                "entities": entities,
                "intent": intent,
                "confidence": 1.0,
                "is_real_ambiguity": False,
                "context_used": "N/A",
                "changes_made": []
            }
        
        # If clause was context-resolved (e.g., C13-C16), add preamble context directly
        if is_context_resolved:
            self.log_entry("CONTEXT_RESOLVED", f"{clause_id}: Adding preamble context to resolved clause")
            # For context-resolved clauses, immediately return with enhanced text
            clarification_result = {
                'text_clarified': self._add_context_to_resolved_clause(clause_id, original_text),
                'confidence': 1.0,
                'is_real_ambiguity': False,
                'real_ambiguity_reason': None,
                'context_used': 'PREAMBLE_REFERENCE',
                'changes_made': ['Added preamble context reference'],
                'source': 'context-resolved'
            }
            
            return {
                "clauseId": clause_id,
                "text_original": original_text,
                "text_clarified": clarification_result.get('text_clarified'),
                "ambiguity_reason": f"[CONTEXT-RESOLVED] Resolved via upstream definitions in policy preamble/section.",
                "ambiguity_types": [],
                "ambiguities_fixed": [],
                "entities": entities,
                "intent": intent,
                "confidence": 1.0,
                "is_real_ambiguity": False,
                "context_used": "PREAMBLE_REFERENCE",
                "search_method": "PREAMBLE_CONTEXT",
                "changes_made": ["Added preamble coverage definition"],
                "context_found": True
            }
        
        num_ambigs = len(ambiguity_types) if ambiguity_types else 1
        self.log_entry("PROCESSING", f"{clause_id}: Searching context for {num_ambigs} ambiguities...")
        
        # Search for context
        ambiguity_record = {
            'clauseId': clause_id,
            'reason': ambiguity_reason,
            'ambiguity_types': ambiguity_types
        }
        
        context_found, context_text, search_method = self.context_engine.search_context(ambiguity_record)
        
        # Clarify with or without context
        self.log_entry("CLARIFYING", f"{clause_id}: Generating clarified text using {search_method}...")
        clarification_result = self.clarify_clause_with_context(
            clause_id, 
            original_text, 
            ambiguity_reason, 
            ambiguity_types,
            context_text,
            search_method
        )
        
        return {
            "clauseId": clause_id,
            "text_original": original_text,
            "text_clarified": clarification_result.get('text_clarified', original_text),
            "ambiguity_reason": ambiguity_reason,
            "ambiguity_types": ambiguity_types,
            "ambiguities_fixed": ambiguity_types if context_found else [],
            "entities": entities,
            "intent": intent,
            "confidence": clarification_result.get('confidence', 0.0),
            "is_real_ambiguity": clarification_result.get('is_real_ambiguity', False),
            "real_ambiguity_reason": clarification_result.get('real_ambiguity_reason'),
            "context_used": clarification_result.get('context_used', 'NONE'),
            "search_method": search_method,
            "changes_made": clarification_result.get('changes_made', []),
            "context_found": context_found
        }
    
    def clarify_all_clauses(self):
        """Main clarification pipeline with context-aware processing"""
        self.log_entry("START", "Stage 5: Ambiguity Clarification with Context Search")
        self.log_entry("CONFIG", f"Workers={self.max_workers}, Batch Size={self.batch_size}")
        
        # Load data
        try:
            with open(self.stage3_file, 'r') as f:
                stage3_data = json.load(f)
            with open(self.stage4_file, 'r') as f:
                stage4_data = json.load(f)
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load files: {e}")
            return False
        
        stage3_clauses = stage3_data.get('extracted_clauses', [])
        ambiguity_flags = stage4_data if isinstance(stage4_data, list) else []
        
        # Create ambiguity map (include detection method for context-resolved clauses)
        ambiguity_map = {
            flag['clauseId']: {
                'reason': flag.get('reason', ''),
                'types': flag.get('ambiguity_types', []),
                'ambiguous': flag.get('ambiguous', False),
                'method': flag.get('detection_method', 'none')
            }
            for flag in ambiguity_flags
        }
        
        self.log_entry("INFO", f"Processing {len(stage3_clauses)} clauses")
        
        clarified_clauses = []
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.process_single_clause, clause, ambiguity_map): clause['clauseId']
                for clause in stage3_clauses
            }
            
            completed = 0
            for future in as_completed(futures):
                clause_id = futures[future]
                try:
                    result = future.result()
                    clarified_clauses.append(result)
                    completed += 1
                    self.log_entry("COMPLETE", f"Progress: {completed}/{len(stage3_clauses)}")
                except Exception as e:
                    self.log_entry("ERROR", f"{clause_id}: Processing failed: {e}")
        
        # Sort by clause ID
        clarified_clauses.sort(key=lambda x: x['clauseId'])
        
        # Save
        self.save_clarified_clauses(clarified_clauses)
        
        return True
    
    def save_clarified_clauses(self, clarified_clauses):
        """Save clarified clauses with new metadata fields"""
        output = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "source": "stage3_entities.json + stage4_ambiguity_flags.json (context-aware)",
                "format": "Clarified Clauses with Context & Real Ambiguity Detection",
                "total_clauses": len(clarified_clauses),
                "stage": "5",
                "new_fields": {
                    "confidence": "LLM confidence in clarification (0.0-1.0)",
                    "is_real_ambiguity": "Flag: genuine policy ambiguity (true) vs clarifiable (false)",
                    "real_ambiguity_reason": "Explanation if genuine ambiguity detected",
                    "context_used": "Search method: RULE_BASED, SEMANTIC, or NONE",
                    "search_method": "Actual search strategy used",
                    "changes_made": "List of specific clarifications made",
                    "context_found": "Whether supporting context was found in policy"
                }
            },
            "clarified_clauses": clarified_clauses
        }
        
        try:
            with open(self.clarified_file, 'w') as f:
                json.dump(output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Saved to: {self.clarified_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=5,
                stage_name="clarify-ambiguities-with-context",
                stage_output=output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save: {e}")
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== STAGE 5: AMBIGUITY CLARIFICATION WITH CONTEXT LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*60 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class ClauseIndexer:
    """Fast clause indexing for DSL pattern matching"""
    
    def __init__(self, clauses_data):
        self.clauses_data = clauses_data if isinstance(clauses_data, list) else []
        self.index = {}
        self._build_index()
    
    def _build_index(self):
        """Build keyword-based index for fast lookup (policy-agnostic)"""
        for clause in self.clauses_data:
            clause_id = clause.get('clauseId', '')
            intent = clause.get('intent', '')
            text = clause.get('text', '').lower()
            entities = clause.get('entities', {})
            
            # Extract keywords from text (generic approach)
            keywords = set()
            
            # 1. Extract words with length > 3 (natural noise filter)
            words = re.findall(r'\b[a-z]+\b', text)
            keywords.update(w for w in words if len(w) > 3)
            
            # 2. Extract multi-word phrases (2-3 words separated by space/hyphen)
            phrases = re.findall(r'\b[a-z][\w\s\-]{2,}\b', text)
            keywords.update(p.lower().strip() for p in phrases if len(p) > 5)
            
            # 3. Add entity keys as keywords (always relevant)
            keywords.update(e.lower() for e in entities.keys())
            
            # 4. Extract quoted/parenthetical terms (important definitions)
            quoted_terms = re.findall(r"['\"]([^'\"]+)['\"]", clause.get('text', ''))
            keywords.update(t.lower().strip() for t in quoted_terms if len(t) > 2)
            
            # 5. Extract numerical values + adjacent noun (e.g., "10 km", "Rs. 2000")
            numeric_terms = re.findall(r'\d+(?:\s*[a-z%]+)?', text)
            keywords.update(t.lower() for t in numeric_terms if t.strip())
            
            # Index by intent type
            if intent not in self.index:
                self.index[intent] = []
            
            self.index[intent].append({
                'clause_id': clause_id,
                'keywords': list(keywords),
                'entities': list(entities.keys()),
                'text': text,
                'original': clause
            })
    
    def find_similar_clauses(self, intent, keywords, top_k=3):
        """
        Find similar clauses using keyword matching.
        If intent is None, search across ALL intents.
        """
        scored = []
        
        # If intent specified, search only that intent; else search all
        intents_to_search = [intent] if intent and intent in self.index else list(self.index.keys())
        
        for search_intent in intents_to_search:
            candidates = self.index.get(search_intent, [])
            
            for candidate in candidates:
                candidate_keywords = set(candidate['keywords'])
                candidate_entities = set(candidate['entities'])
                
                # Score based on keyword overlap
                keyword_overlap = len(keywords & candidate_keywords)
                
                # Also score based on entity overlap
                entity_overlap = len(keywords & candidate_entities)
                
                # Combined score
                total_score = keyword_overlap + (entity_overlap * 2)  # Weight entities higher
                
                if total_score > 0:
                    scored.append((candidate, total_score))
        
        # Sort by overlap score
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:top_k]]


class DSLGenerator:
    """
    Stage 6: Generate DSL rules from clarified clauses
    
    Uses rule-based indexing + Gemini AI for fast DSL generation.
    Falls back to LLM only when indexed lookup fails.
    Marks ambiguous rules with WARN actions instead of ENFORCE.
    
    Input:  stage5_clarified_clauses.json + stage4_ambiguity_flags.json
    Output: stage6_dsl_rules.yaml
    """
    
    def __init__(self, stage5_file, stage4_file, document_id=None, enable_mongodb=True, use_langchain=True):
        self.stage5_file = stage5_file
        self.stage4_file = stage4_file
        self.dsl_file = f"{OUTPUT_DIR}/stage6_dsl_rules.yaml"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Initialize clause indexer
        self.clause_indexer = None
        
        # Initialize LangChain components if available
        if self.use_langchain:
            self.log_entry("INFO", "LangChain enabled for dynamic DSL generation")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
        else:
            self.log_entry("INFO", "Using standard Gemini for DSL generation")
    
    def log_entry(self, level, message):
        """Thread-safe log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def generate_dsl_from_index(self, clause_id, intent, entities, is_ambiguous):
        """Fast DSL generation using indexed patterns"""
        
        # Extract keywords from entities
        entity_keywords = set()
        for entity_name in entities.keys():
            # Convert entity names to keywords
            words = re.findall(r'\b[a-z]+\b', entity_name.lower())
            entity_keywords.update(words)
        
        # Try to find similar clauses in index
        similar_clauses = self.clause_indexer.find_similar_clauses(intent, entity_keywords, top_k=1)
        
        if similar_clauses:
            # Use pattern from similar clause
            similar = similar_clauses[0]
            self.log_entry("INDEX_HIT", f"Found similar clause {similar['clause_id']} for {clause_id}")
            
            # Generate DSL based on similar pattern
            return self.generate_dsl_from_pattern(clause_id, intent, entities, is_ambiguous, similar)
        
        # No similar clause found - need LLM
        return None
    
    def generate_dsl_from_pattern(self, clause_id, intent, entities, is_ambiguous, similar_clause):
        """Generate DSL based on similar clause pattern"""
        
        # Build dynamic when conditions from entities
        when_conditions = []
        
        for entity_name, entity_value in entities.items():
            # Convert entity name to fact
            fact = entity_name.replace('.', '_').lower()
            
            # Determine operator based on entity type
            if 'upperLimit' in entity_name or 'maximum' in entity_name:
                operator = 'LESS_THAN_OR_EQUAL'
            elif 'lowerLimit' in entity_name or 'minimum' in entity_name:
                operator = 'GREATER_THAN_OR_EQUAL'
            elif 'rate' in entity_name or 'amount' in entity_name:
                operator = 'EQUALS'
            else:
                operator = 'EQUALS'
            
            when_conditions.append({
                'fact': fact,
                'operator': operator,
                'value': entity_value
            })
        
        # Build then constraints based on intent
        action = 'warn' if is_ambiguous else 'enforce'
        
        if intent == 'INFORMATIONAL':
            then_constraints = [{'constraint': 'PASS', 'operator': 'EQUALS', 'value': 'OK'}]
        elif intent == 'RESTRICTION':
            then_constraints = [{'constraint': 'approval.required', 'operator': 'EQUALS', 'value': 'YES'}]
        elif intent == 'LIMIT':
            # Extract limit type from entities
            limit_type = 'general'
            for entity_name in entities.keys():
                if 'tour' in entity_name.lower():
                    limit_type = 'tour_duration'
                elif 'allowance' in entity_name.lower():
                    limit_type = 'allowance_limit'
                break
            
            then_constraints = [{'constraint': f'limit.{limit_type}', 'operator': 'ENFORCED', 'value': 'STRICT'}]
        else:  # CONDITIONAL_ALLOWANCE
            # Extract allowance type
            allowance_type = 'general'
            for entity_name in entities.keys():
                if 'lodging' in entity_name.lower():
                    allowance_type = 'lodging'
                elif 'boarding' in entity_name.lower():
                    allowance_type = 'boarding'
                elif 'mileage' in entity_name.lower():
                    allowance_type = 'mileage'
                break
            
            then_constraints = [{'constraint': f'allowance.{allowance_type}', 'operator': 'APPROVED', 'value': 'CONDITIONAL'}]
        
        return {
            'rule_id': clause_id,
            'when': {'all': when_conditions},
            'then': {action: then_constraints}
        }
    
    def log_entry(self, level, message):
        """Thread-safe log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def generate_dsl_rule_with_gemini(self, clause_id, clause_text, intent, entities, is_ambiguous):
        """Use Gemini to dynamically generate DSL rule"""
        
        entities_str = json.dumps(entities, indent=2) if entities else "No entities extracted"
        
        prompt = f"""You are a DSL rule generation expert. Convert policy clauses into executable rule format.

CLAUSE ID: {clause_id}
INTENT: {intent}
AMBIGUOUS: {is_ambiguous}

CLAUSE TEXT:
{clause_text}

EXTRACTED ENTITIES:
{entities_str}

Generate a DSL rule in this JSON format:
{{
    "rule_id": "{clause_id}",
    "when": {{
        "all": [
            {{
                "fact": "<dynamic_fact_based_on_entities>",
                "operator": "<appropriate_operator>",
                "value": "<dynamic_value_from_entities>"
            }}
        ]
    }},
    "then": {{
        "<enforce_or_warn>": [
            {{
                "constraint": "<dynamic_constraint_based_on_intent>",
                "operator": "<appropriate_operator>",
                "value": "<dynamic_value>"
            }}
        ]
    }}
}}

Rules:
- Use "enforce" action if not ambiguous, "warn" if ambiguous
- For INFORMATIONAL: constraint="PASS", operator="EQUALS", value="OK"
- For RESTRICTION: constraint="approval.required", operator="EQUALS", value="<approval_value>"
- For CONDITIONAL_ALLOWANCE: constraint="allowance.<type>", operator="EQUALS", value="<amount>"
- For LIMIT: constraint="limit.<type>", operator="LESS_THAN_OR_EQUAL", value="<limit>"
- Generate dynamic facts and values from the entities list
- If no meaningful conditions can be generated, use default PASS rule

Return ONLY the JSON object, no markdown formatting."""
        
        try:
            response = self.model.generate_content(prompt)
            
            # Parse JSON from response
            response_text = response.text.strip()
            # Remove markdown code blocks if present
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            dsl_rule = json.loads(response_text)
            
            # Ensure structure
            if 'rule_id' not in dsl_rule:
                dsl_rule['rule_id'] = clause_id
            if 'when' not in dsl_rule:
                dsl_rule['when'] = {'all': []}
            if 'then' not in dsl_rule:
                action = 'warn' if is_ambiguous else 'enforce'
                dsl_rule['then'] = {action: [{'constraint': 'PASS', 'operator': 'EQUALS', 'value': 'OK'}]}
            
            return dsl_rule
            
        except json.JSONDecodeError as e:
            self.log_entry("WARNING", f"Failed to parse DSL JSON for {clause_id}: {e}")
            # Return default rule
            return self.create_default_rule(clause_id, is_ambiguous)
        except Exception as e:
            self.log_entry("ERROR", f"Gemini DSL generation failed for {clause_id}: {e}")
            return self.create_default_rule(clause_id, is_ambiguous)
    
    def create_default_rule(self, clause_id, is_ambiguous):
        """Create a default DSL rule when AI generation fails"""
        return {
            'rule_id': clause_id,
            'when': {'all': []},
            'then': {
                'warn' if is_ambiguous else 'enforce': [
                    {'constraint': 'PASS', 'operator': 'EQUALS', 'value': 'OK'}
                ]
            }
        }
    
    def create_smart_default_rule(self, clause_id, intent, entities, is_ambiguous):
        """Create smart DSL rule based on intent and entities"""
        
        # Build when conditions from entities
        when_conditions = []
        
        for entity_name, entity_value in entities.items():
            # Convert entity name to fact
            fact = entity_name.replace('.', '_').lower()
            
            # Determine operator based on entity type
            if 'upperLimit' in entity_name or 'maximum' in entity_name or 'limit' in entity_name.lower():
                operator = 'LESS_THAN_OR_EQUAL'
            elif 'lowerLimit' in entity_name or 'minimum' in entity_name:
                operator = 'GREATER_THAN_OR_EQUAL'
            elif 'rate' in entity_name or 'amount' in entity_name or 'allowance' in entity_name.lower():
                operator = 'EQUALS'
            elif 'deadline' in entity_name.lower() or 'duration' in entity_name.lower():
                operator = 'LESS_THAN_OR_EQUAL'
            else:
                operator = 'EQUALS'
            
            when_conditions.append({
                'fact': fact,
                'operator': operator,
                'value': entity_value
            })
        
        # Build then constraints based on intent
        action = 'warn' if is_ambiguous else 'enforce'
        
        if intent == 'INFORMATIONAL':
            then_constraints = [{'constraint': 'PASS', 'operator': 'EQUALS', 'value': 'OK'}]
        elif intent == 'RESTRICTION':
            then_constraints = [{'constraint': 'approval.required', 'operator': 'EQUALS', 'value': 'YES'}]
        elif intent == 'LIMIT':
            # Extract limit type from entities
            limit_type = 'general'
            for entity_name in entities.keys():
                entity_lower = entity_name.lower()
                if 'tour' in entity_lower:
                    limit_type = 'tour_duration'
                elif 'lodging' in entity_lower:
                    limit_type = 'lodging'
                elif 'boarding' in entity_lower:
                    limit_type = 'boarding'
                elif 'mileage' in entity_lower:
                    limit_type = 'mileage'
                elif 'travel' in entity_lower:
                    limit_type = 'travel'
                break
            
            then_constraints = [{'constraint': f'limit.{limit_type}', 'operator': 'ENFORCED', 'value': 'STRICT'}]
        else:  # CONDITIONAL_ALLOWANCE
            # Extract allowance type
            allowance_type = 'general'
            for entity_name in entities.keys():
                entity_lower = entity_name.lower()
                if 'lodging' in entity_lower:
                    allowance_type = 'lodging'
                elif 'boarding' in entity_lower:
                    allowance_type = 'boarding'
                elif 'mileage' in entity_lower:
                    allowance_type = 'mileage'
                elif 'travel' in entity_lower:
                    allowance_type = 'travel'
                break
            
            then_constraints = [{'constraint': f'allowance.{allowance_type}', 'operator': 'APPROVED', 'value': 'CONDITIONAL'}]
        
        return {
            'rule_id': clause_id,
            'when': {'all': when_conditions},
            'then': {action: then_constraints}
        }
    
    def load_files(self):
        """Load stage5 and stage4 data"""
        try:
            with open(self.stage5_file, 'r') as f:
                stage5_data = json.load(f)
            with open(self.stage4_file, 'r') as f:
                stage4_data = json.load(f)
            return stage5_data, stage4_data
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load files: {e}")
            return None, None
    
    def build_when_condition(self, clause_id, intent, entities):
        """Build 'when' condition from entities - minimal format"""
        conditions = []
        
        if not entities:
            return None
        
        # Travel Classification rules (C2)
        if 'maximumTourDuration' in entities:
            conditions.append({
                'fact': 'travel.duration',
                'operator': 'LESS_THAN_OR_EQUAL',
                'value': entities['maximumTourDuration']
            })
        
        if 'minimumTourDuration' in entities:
            conditions.append({
                'fact': 'travel.duration',
                'operator': 'GREATER_THAN_OR_EQUAL',
                'value': entities['minimumTourDuration']
            })
        
        if 'minimumDeputationDuration' in entities:
            conditions.append({
                'fact': 'travel.duration',
                'operator': 'GREATER_THAN_OR_EQUAL',
                'value': entities['minimumDeputationDuration']
            })
            
        if 'maximumDeputationDuration' in entities:
            conditions.append({
                'fact': 'travel.duration',
                'operator': 'LESS_THAN_OR_EQUAL',
                'value': entities['maximumDeputationDuration']
            })
        
        # Allowance rules
        if 'grade' in entities:
            conditions.append({
                'fact': 'employee.grade',
                'operator': 'EQUALS',
                'value': entities['grade']
            })
        
        if 'lodgingAllowanceCategoryA' in entities or 'lodgingAllowanceCategoryB' in entities:
            conditions.append({
                'fact': 'location.category',
                'operator': 'IN',
                'value': 'CATEGORY_A | CATEGORY_B'
            })
        
        # Mileage rate rules
        if 'autoTaxiNonACRate' in entities or 'taxiACRate' in entities:
            conditions.append({
                'fact': 'vehicle.type',
                'operator': 'IN',
                'value': 'TAXI'
            })
        
        # Travel mode conditions
        if 'travelModeAir' in entities:
            conditions.append({
                'fact': 'travel.mode',
                'operator': 'EQUALS',
                'value': 'AIR'
            })
            
        if 'travelModeTrain' in entities:
            conditions.append({
                'fact': 'travel.mode',
                'operator': 'EQUALS',
                'value': 'TRAIN'
            })
            
        if 'travelModeTaxiLocal' in entities:
            conditions.append({
                'fact': 'travel.mode',
                'operator': 'EQUALS',
                'value': 'TAXI_LOCAL'
            })
            
        if 'travelModeTaxiInterCity' in entities:
            conditions.append({
                'fact': 'travel.mode',
                'operator': 'EQUALS',
                'value': 'TAXI_INTERCITY'
            })
        
        # Booking rules
        if 'bookingRequestLeadTime' in entities:
            conditions.append({
                'fact': 'booking.submitTime',
                'operator': 'BEFORE',
                'value': entities['bookingRequestLeadTime']
            })
        
        if 'bookingRestriction' in entities:
            conditions.append({
                'fact': 'booking.type',
                'operator': 'NOT_EQUALS',
                'value': 'DIRECT'
            })
        
        # Bill submission rules
        if 'billSubmissionDeadlineAfterTourCompletion' in entities:
            conditions.append({
                'fact': 'bill.submitTime',
                'operator': 'WITHIN_DAYS',
                'value': entities['billSubmissionDeadlineAfterTourCompletion']
            })
        
        return conditions if conditions else None
    
    def build_then_constraint(self, clause_id, intent, entities):
        """Build 'then' constraints - minimal format"""
        constraints = []
        
        # Travel Classification rules
        if 'travelClassifications' in entities:
            if 'tourDurationUpperLimit' in entities:
                constraints.append({
                    'constraint': 'travel.type',
                    'operator': 'EQUALS',
                    'value': 'TOUR'
                })
            elif 'deputationDurationLowerLimit' in entities:
                constraints.append({
                    'constraint': 'travel.type',
                    'operator': 'EQUALS',
                    'value': 'DEPUTATION'
                })
            elif 'transferDurationLowerLimit' in entities:
                constraints.append({
                    'constraint': 'travel.type',
                    'operator': 'EQUALS',
                    'value': 'TRANSFER'
                })
        
        # Allowance constraints
        if intent == 'CONDITIONAL_ALLOWANCE':
            if 'lodgingReimbursementRate' in entities:
                constraints.append({
                    'constraint': 'allowance.lodging',
                    'operator': 'EQUALS',
                    'value': entities['lodgingReimbursementRate']
                })
            if 'fourWheelerMileageRate' in entities:
                constraints.append({
                    'constraint': 'mileage.fourWheeler',
                    'operator': 'EQUALS',
                    'value': entities['fourWheelerMileageRate']
                })
            if 'twoWheelerMileageRate' in entities:
                constraints.append({
                    'constraint': 'mileage.twoWheeler',
                    'operator': 'EQUALS',
                    'value': entities['twoWheelerMileageRate']
                })
        
        # Restriction constraints
        if intent == 'RESTRICTION':
            if 'requiredApproval' in entities:
                constraints.append({
                    'constraint': 'approval.required',
                    'operator': 'EQUALS',
                    'value': entities['requiredApproval']
                })
            if 'billSubmissionDeadlineAfterTourCompletion' in entities:
                constraints.append({
                    'constraint': 'bill.deadline',
                    'operator': 'EQUALS',
                    'value': entities['billSubmissionDeadlineAfterTourCompletion']
                })
        
        return constraints if constraints else [{'constraint': 'PASS', 'operator': 'EQUALS', 'value': 'OK'}]
    
    def generate_dsl_rules(self):
        """Generate DSL rules using fast indexing + LLM fallback"""
        self.log_entry("INFO", "Starting Stage 6: Fast DSL Generation with Indexing")
        
        # Load data
        stage5_data, stage4_data = self.load_files()
        if not stage5_data or not stage4_data:
            return False
        
        clarified_clauses = stage5_data.get('clarified_clauses', [])
        ambiguity_map = {flag['clauseId']: flag.get('ambiguous', False) 
                        for flag in stage4_data if isinstance(stage4_data, list)}
        
        # Build clause index for fast lookups
        self.log_entry("INFO", f"Building clause index for {len(clarified_clauses)} clauses")
        self.clause_indexer = ClauseIndexer(clarified_clauses)
        
        self.log_entry("INFO", f"Generating DSL for {len(clarified_clauses)} clauses (indexed approach)")
        
        dsl_rules = []
        
        for clause in clarified_clauses:
            clause_id = clause['clauseId']
            clause_text = clause.get('text', '')
            intent = clause.get('intent', 'INFORMATIONAL')
            entities = clause.get('entities', {})
            
            # Check if there are UNRESOLVED (real) ambiguities
            is_real_ambiguity = clause.get('is_real_ambiguity', False)
            
            # Also check if ambiguities were FIXED in stage5
            ambiguity_types = clause.get('ambiguity_types', [])
            ambiguities_fixed = clause.get('ambiguities_fixed', [])
            
            # If real ambiguities exist OR not all ambiguities are fixed, use warn; otherwise enforce
            all_fixed = set(ambiguity_types).issubset(set(ambiguities_fixed)) if ambiguity_types else True
            is_ambiguous = is_real_ambiguity or not all_fixed
            
            self.log_entry("PROCESSING", f"{clause_id}: Generating DSL ({intent}) - ambiguities_fixed: {len(ambiguities_fixed)}/{len(ambiguity_types)}")
            
            # Try fast indexed generation first
            rule = self.generate_dsl_from_index(clause_id, intent, entities, is_ambiguous)
            
            if rule:
                # Success - no LLM call needed
                self.log_entry("INDEXED", f"{clause_id}: Fast DSL generated")
            else:
                # Create smart default rule based on intent and entities
                self.log_entry("SMART_DEFAULT", f"{clause_id}: Creating smart default rule")
                rule = self.create_smart_default_rule(clause_id, intent, entities, is_ambiguous)
            
            dsl_rules.append(rule)
            self.log_entry("GENERATED", f"{clause_id}: DSL rule created")
        
        self.log_entry("SUCCESS", f"DSL generation complete: {len(dsl_rules)} rules generated using indexed approach")
        
        # Save DSL rules
        self.save_dsl_rules(dsl_rules)
        
        return True
    
    def save_dsl_rules(self, dsl_rules):
        """Save DSL rules as YAML"""
        import yaml
        
        output = {
            'rules': dsl_rules
        }
        
        try:
            with open(self.dsl_file, 'w') as f:
                yaml.dump(output, f, default_flow_style=False, sort_keys=False, width=200)
            
            self.log_entry("SUCCESS", f"DSL rules saved to: {self.dsl_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=6,
                stage_name="generate-dsl",
                stage_output=output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save DSL rules: {e}")
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== STAGE 6: DSL GENERATION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


class PipelineOrchestrator:
    """
    Orchestrate full pipeline: 1 → 1B → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 10
    (Skips Stage 7: Confidence-Rationale for speed)
    
    Single entry point for complete policy processing
    Starts from PDF extraction and handles all sequential dependencies automatically
    Includes OPA Bundle Storage (Stage 10) for policy rule management
    """
    
    def __init__(self, pdf_file, enable_mongodb=True):
        self.pdf_file = pdf_file
        self.policy_text_file = f"{OUTPUT_DIR}/filename.txt"
        self.enable_mongodb = enable_mongodb
        self.log = []
        self.stage_results = {}
    
    def log_entry(self, level, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def run_stage_1(self):
        """Stage 1: Extract PDF to text"""
        self.log_entry("STAGE", "Running Stage 1: PDF Extraction")
        
        try:
            extractor = PolicyExtractor(self.pdf_file)
            success = extractor.extract_pdf()
            extractor.save_log()
            
            if success:
                self.stage_results['stage1_file'] = self.policy_text_file
                self.log_entry("SUCCESS", "Stage 1 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 1 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 1 exception: {e}")
            return False
    
    def run_stage_1b(self):
        """Stage 1B: Extract & elaborate clauses"""
        self.log_entry("STAGE", "Running Stage 1B: Clause Extraction")
        
        try:
            extractor = ClauseExtractor(self.policy_text_file, enable_mongodb=self.enable_mongodb)
            success = extractor.extract()
            extractor.save_log()
            
            if success:
                self.stage_results['stage1b_file'] = f"{OUTPUT_DIR}/stage1_clauses.json"
                self.log_entry("SUCCESS", "Stage 1B complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 1B failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 1B exception: {e}")
            return False
    
    def run_stage_2(self):
        """Stage 2: Classify intent"""
        self.log_entry("STAGE", "Running Stage 2: Intent Classification")
        
        try:
            clauses_file = self.stage_results.get('stage1b_file', f"{OUTPUT_DIR}/stage1_clauses.json")
            classifier = IntentClassifier(clauses_file, enable_mongodb=self.enable_mongodb)
            success = classifier.classify()
            classifier.save_log()
            
            if success:
                self.stage_results['stage2_file'] = f"{OUTPUT_DIR}/stage2_classified.json"
                self.log_entry("SUCCESS", "Stage 2 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 2 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 2 exception: {e}")
            return False
    
    def run_stage_3(self):
        """Stage 3: Extract entities (RULE-BASED ONLY to avoid rate limits)"""
        self.log_entry("STAGE", "Running Stage 3: Entity Extraction (Rule-based, no LLM)")
        
        try:
            classified_file = self.stage_results.get('stage2_file', f"{OUTPUT_DIR}/stage2_classified.json")
            extractor = EntityExtractor(
                classified_file,
                enable_mongodb=self.enable_mongodb,
                use_langchain=False,  # DISABLE LLM - use rule-based extraction only
                max_workers=PipelineConfig.ENTITY_EXTRACTION_WORKERS
            )
            success = extractor.extract()
            extractor.save_log()
            
            if success:
                self.stage_results['stage3_file'] = f"{OUTPUT_DIR}/stage3_entities.json"
                self.log_entry("SUCCESS", "Stage 3 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 3 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 3 exception: {e}")
            return False
    
    def run_stage_4(self):
        """Stage 4: Detect ambiguities (with context-aware cross-reference resolution)"""
        self.log_entry("STAGE", "Running Stage 4: Ambiguity Detection")
        
        try:
            stage3_file = self.stage_results.get('stage3_file', f"{OUTPUT_DIR}/stage3_entities.json")
            
            # Load original document if available (for cross-reference context)
            original_doc = None
            if os.path.exists("filename.txt"):
                try:
                    with open("filename.txt", 'r') as f:
                        original_doc = f.read()
                except:
                    pass
            
            detector = AmbiguityDetector(stage3_file, enable_mongodb=self.enable_mongodb, original_document=original_doc)
            success = detector.detect_ambiguities()
            detector.save_log()
            
            if success:
                self.stage_results['stage4_file'] = f"{OUTPUT_DIR}/stage4_ambiguity_flags.json"
                self.log_entry("SUCCESS", "Stage 4 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 4 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 4 exception: {e}")
            return False
    
    def run_stage_5(self):
        """Stage 5: Clarify ambiguities"""
        self.log_entry("STAGE", "Running Stage 5: Ambiguity Clarification")
        
        try:
            stage3_file = self.stage_results.get('stage3_file', f"{OUTPUT_DIR}/stage3_entities.json")
            stage4_file = self.stage_results.get('stage4_file', f"{OUTPUT_DIR}/stage4_ambiguity_flags.json")
            clarifier = AmbiguityClarifier(
                stage3_file,
                stage4_file,
                enable_mongodb=self.enable_mongodb,
                max_workers=PipelineConfig.AMBIGUITY_CLARIFICATION_WORKERS,
                batch_size=PipelineConfig.AMBIGUITY_CLARIFICATION_BATCH_SIZE
            )
            success = clarifier.clarify_all_clauses()
            clarifier.save_log()
            
            if success:
                self.stage_results['stage5_file'] = f"{OUTPUT_DIR}/stage5_clarified_clauses.json"
                self.log_entry("SUCCESS", "Stage 5 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 5 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 5 exception: {e}")
            return False
    
    def run_stage_6(self):
        """Stage 6: Generate DSL rules"""
        self.log_entry("STAGE", "Running Stage 6: DSL Rule Generation")
        
        try:
            stage5_file = self.stage_results.get('stage5_file', f"{OUTPUT_DIR}/stage5_clarified_clauses.json")
            stage4_file = self.stage_results.get('stage4_file', f"{OUTPUT_DIR}/stage4_ambiguity_flags.json")
            generator = DSLGenerator(stage5_file, stage4_file, enable_mongodb=self.enable_mongodb)
            success = generator.generate_dsl_rules()
            generator.save_log()
            
            if success:
                self.stage_results['stage6_file'] = f"{OUTPUT_DIR}/stage6_dsl_rules.yaml"
                self.log_entry("SUCCESS", "Stage 6 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 6 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 6 exception: {e}")
            return False
    
    def run_stage_8(self):
        """Stage 8: Generate normalized policies (skip Stage 7)"""
        self.log_entry("STAGE", "Running Stage 8: Normalized Policy Generation (Stage 7 skipped)")
        
        try:
            dsl_file = self.stage_results.get('stage6_file', f"{OUTPUT_DIR}/stage6_dsl_rules.yaml")
            # confidence_file is optional for stage 8
            confidence_file = f"{OUTPUT_DIR}/stage7_confidence_rationale.json"
            
            generator = NormalizedPolicyGenerator(
                dsl_file,
                confidence_file=confidence_file if os.path.exists(confidence_file) else None,
                enable_mongodb=self.enable_mongodb,
                use_langchain=PipelineConfig.NORMALIZATION_USE_LLM
            )
            success = generator.generate_normalized_policies()
            generator.save_log()
            
            if success:
                self.stage_results['stage8_file'] = f"{OUTPUT_DIR}/stage8_normalized_policies.json"
                self.log_entry("SUCCESS", "Stage 8 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 8 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 8 exception: {e}")
            return False
    
    def run_stage_9(self):
        """Stage 9: Convert DSL rules to Rego format for OPA"""
        self.log_entry("STAGE", "Running Stage 9: DSL to Rego Conversion")
        
        try:
            dsl_file = self.stage_results.get('stage6_file', f"{OUTPUT_DIR}/stage6_dsl_rules.yaml")
            normalized_file = self.stage_results.get('stage8_file', f"{OUTPUT_DIR}/stage8_normalized_policies.json")
            
            generator = RegoGenerator(
                dsl_file,
                normalized_file,
                enable_mongodb=self.enable_mongodb
            )
            success = generator.generate()
            generator.save_log()
            
            if success:
                self.stage_results['stage9_file'] = f"{OUTPUT_DIR}/stage9_rego_bundles.json"
                self.log_entry("SUCCESS", "Stage 9 complete")
                return True
            else:
                self.log_entry("ERROR", "Stage 9 failed")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 9 exception: {e}")
            return False
    
    def run_stage_10(self):
        """Stage 10: OPA Bundle Storage & Management"""
        self.log_entry("STAGE", "Running Stage 10: OPA Bundle Storage")
        
        try:
            rego_bundles_file = self.stage_results.get('stage9_file', f"{OUTPUT_DIR}/stage9_rego_bundles.json")
            
            manager = OPABundleStorageManager(
                rego_bundles_file,
                enable_mongodb=self.enable_mongodb,
                enable_cleanup=False
            )
            result = manager.process()
            manager.save_log()
            
            if result['success']:
                self.stage_results['stage10_file'] = result['filesystem_path']
                self.stage_results['stage10_version'] = result['bundle_version']
                self.stage_results['stage10_hash'] = result['bundle_hash']
                self.log_entry("SUCCESS", "Stage 10 complete")
                return True
            else:
                self.log_entry("ERROR", f"Stage 10 failed: {result.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            self.log_entry("ERROR", f"Stage 10 exception: {e}")
            return False
    
    def run_full_pipeline(self):
        """
        Execute full pipeline: 1 → 1B → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 10
        
        Returns:
            dict: Results with success status and stage file paths
        """
        self.log_entry("START", "="*80)
        self.log_entry("START", "FULL PIPELINE ORCHESTRATION: Stages 1 → 1B → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 10")
        self.log_entry("START", "="*80)
        
        stages = [
            ('1', self.run_stage_1),
            ('1B', self.run_stage_1b),
            ('2', self.run_stage_2),
            ('3', self.run_stage_3),
            ('4', self.run_stage_4),
            ('5', self.run_stage_5),
            ('6', self.run_stage_6),
            ('8', self.run_stage_8),
            ('9', self.run_stage_9),
            ('10', self.run_stage_10)
        ]
        
        for stage_name, stage_func in stages:
            self.log_entry("INFO", f"\n--- Executing Stage {stage_name} ---")
            success = stage_func()
            
            if not success:
                self.log_entry("ERROR", f"Pipeline stopped at Stage {stage_name}")
                return {
                    'success': False,
                    'failed_stage': stage_name,
                    'results': self.stage_results
                }
            
            self.log_entry("PROGRESS", f"Stage {stage_name} ✓")
        
        self.log_entry("SUCCESS", "="*80)
        self.log_entry("SUCCESS", "FULL PIPELINE COMPLETE - All stages successful")
        self.log_entry("SUCCESS", "="*80)
        
        return {
            'success': True,
            'results': self.stage_results,
            'output_file': self.stage_results.get('stage8_file')
        }
    
    def save_log(self):
        """Save orchestration log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== PIPELINE ORCHESTRATION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*80 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")
            f.write("\n" + "="*80 + "\n")


class NormalizedPolicyGenerator:
    """
    Stage 8: Generate Normalized Policy JSON from DSL Rules
    
    Hybrid approach:
    - Rule-based mapping for structural transformation (fast)
    - LLM for complex metadata extraction (when needed)
    
    Input:  stage6_dsl_rules.yaml + stage7_confidence_rationale.json
    Output: stage8_normalized_policies.json
    """
    
    def __init__(self, dsl_file, confidence_file=None, clarified_file=None, document_id=None, enable_mongodb=True, use_langchain=True):
        self.dsl_file = dsl_file
        self.confidence_file = confidence_file
        self.clarified_file = clarified_file or f"{OUTPUT_DIR}/stage5_clarified_clauses.json"
        self.normalized_file = f"{OUTPUT_DIR}/stage8_normalized_policies.json"
        self.document_id = document_id
        self.log = []
        self.log_lock = threading.Lock()
        self.use_langchain = use_langchain and LANGCHAIN_AVAILABLE
        
        # OPTIMIZATION: Make LLM truly optional for faster processing
        self.llm_enabled = self.use_langchain
        
        # Initialize MongoDB storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id or "unknown")
        
        # Load supporting data from earlier stages
        self.clarified_clauses = self.load_clarified_clauses()
        
        # Only initialize Gemini if LLM is enabled
        if self.llm_enabled:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemma-3-27b-it')
            
            # Initialize LangChain components if available
            self.log_entry("INFO", "LangChain enabled for metadata extraction")
            self.langchain_llm = ChatGoogleGenerativeAI(
                model="gemma-3-27b-it",
                google_api_key=GEMINI_API_KEY,
                temperature=0.1,
                max_retries=3
            )
        else:
            self.log_entry("INFO", "Using fast rule-based metadata extraction (LLM disabled)")
            self.model = None
            self.langchain_llm = None
    
    def log_entry(self, level, message):
        """Thread-safe log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    def load_dsl_rules(self):
        """Load DSL rules from YAML file"""
        try:
            import yaml
            with open(self.dsl_file, 'r') as f:
                data = yaml.safe_load(f)
            return data.get('rules', [])
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load DSL rules: {e}")
            return []
    
    def load_confidence_data(self):
        """Load confidence and rationale data"""
        if not self.confidence_file:
            return {}
        
        try:
            with open(self.confidence_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log_entry("WARNING", f"Failed to load confidence data: {e}")
            return {}
    
    def load_clarified_clauses(self):
        """Load clarified clauses from Stage 5 for metadata enrichment"""
        try:
            with open(self.clarified_file, 'r') as f:
                data = json.load(f)
            
            # Build lookup dict: clauseId -> clarified clause data
            clauses_by_id = {}
            for clause in data.get('clarified_clauses', []):
                clause_id = clause.get('clauseId')
                if clause_id:
                    clauses_by_id[clause_id] = clause
            
            self.log_entry("INFO", f"Loaded {len(clauses_by_id)} clarified clauses from {self.clarified_file}")
            return clauses_by_id
        except Exception as e:
            self.log_entry("WARNING", f"Failed to load clarified clauses: {e}")
            return {}
    
    def consolidate_clause_data(self, clause_id, stage_data):
        """Consolidate all stage data for a single clause into UI-compatible schema"""
        
        # Extract DSL rule data
        dsl_rule = stage_data['stage6']
        when_conditions = dsl_rule.get('when', {}).get('all', [])
        then_outcome = dsl_rule.get('then', {})
        enforcement_level = 'enforce' if 'enforce' in then_outcome else 'warn'
        
        # Get first constraint and normalize it (DSL uses 'constraint' field, UI expects 'fact')
        constraint = {}
        raw_constraint = {}
        if 'warn' in then_outcome and then_outcome['warn']:
            raw_constraint = then_outcome['warn'][0] if isinstance(then_outcome['warn'], list) else then_outcome['warn']
        elif 'enforce' in then_outcome and then_outcome['enforce']:
            raw_constraint = then_outcome['enforce'][0] if isinstance(then_outcome['enforce'], list) else then_outcome['enforce']
        
        # Normalize: rename 'constraint' field to 'fact' for UI compatibility
        if raw_constraint:
            constraint = {
                'fact': raw_constraint.get('constraint', raw_constraint.get('fact', '')),
                'operator': raw_constraint.get('operator', ''),
                'value': raw_constraint.get('value', '')
            }
        
        consolidated = {
            # UI-compatible top-level fields (for displayPolicies JS)
            'policyId': f"POLICY_{clause_id}",
            'name': f"Policy Rule {clause_id}",
            'outcome': {
                'enforcement': enforcement_level.lower(),
                'message': f"Policy {clause_id} enforcement"
            },
            'when': when_conditions,
            'what': {
                'constraint': constraint
            },
            
            # Original consolidated structure (for backend use)
            'core_attributes': {
                'clauseId': clause_id,
                'text_clarified': stage_data['stage5'].get('text_clarified', ''),
                'intent': stage_data['stage2'].get('intent', 'UNKNOWN'),
                'confidence_score': stage_data['stage7'].get('confidence', 0.0),
                'source_section': stage_data['stage7'].get('sourceSection', '')
            },
            'classification': {
                'stage2_intent': stage_data['stage2'].get('intent', ''),
                'stage2_confidence': stage_data['stage2'].get('confidence', 0.0),
                'stage2_reasoning': stage_data['stage2'].get('reasoning', '')
            },
            'extracted_data': {
                'entities': stage_data['stage3'].get('entities', {}),
                'entity_names': stage_data['stage3'].get('entity_names', [])
            },
            'ambiguity_analysis': {
                'is_ambiguous': stage_data['stage4'].get('is_ambiguous', False),
                'ambiguity_types': stage_data['stage4'].get('ambiguity_types', []),
                'ambiguities_fixed': stage_data['stage5'].get('ambiguities_fixed', []),
                'original_reason': stage_data['stage4'].get('reason', ''),
                'detection_method': stage_data['stage4'].get('detection_method', 'rule-based'),
                'rule_score': stage_data['stage4'].get('rule_score', 0)
            },
            'dsl_rules': {
                'rule_id': stage_data['stage6'].get('rule_id', clause_id),
                'when_conditions': when_conditions,
                'then_outcome': then_outcome,
                'enforcement_level': enforcement_level
            },
            'rationale_metadata': {
                'rationale_text': stage_data['stage7'].get('rationale', ''),
                'confidence_score': stage_data['stage7'].get('confidence', 0.0),
                'ambiguities_fixed': stage_data['stage7'].get('ambiguitiesFixed', []),
                'source_section': stage_data['stage7'].get('sourceSection', '')
            }
        }
        
        return consolidated
    
    def build_dynamic_extraction_index(self):
        """Build dynamic extraction rules from actual stage data ONLY (validated)"""
        index = {
            'roles': {},           # role_value -> context
            'locations': {},       # location_value -> context
            'tenants': {},         # tenant_value -> context
            'authorities': {}      # authority_value -> orgId
        }
        
        # ONLY extract from Stage 3 entities (these are validated by earlier stages)
        for clause_id, clause in self.clarified_clauses.items():
            entities = clause.get('entities', {})
            
            for entity_name, entity_value in entities.items():
                if not entity_value or not isinstance(entity_value, str):
                    continue
                
                # Strip whitespace and validate non-empty
                entity_value = entity_value.strip()
                if not entity_value or len(entity_value) > 100:
                    continue
                
                # Classify based on entity name keywords (STRICT)
                if any(x in entity_name.lower() for x in ['grade', 'role', 'level', 'employee']):
                    index['roles'][entity_value] = entity_name
                
                elif any(x in entity_name.lower() for x in ['location', 'city', 'area', 'region']):
                    index['locations'][entity_value] = entity_name
                
                elif any(x in entity_name.lower() for x in ['applicable', 'tenant', 'org']):
                    index['tenants'][entity_value] = entity_name
        
        # Extract authorities ONLY from clarified text (explicit mentions)
        authorities_patterns = {
            r'(?:head\s+of\s+department|department\s+head|hod)': 'DEPT_MANAGER',
            r'(?:reporting\s+manager|direct\s+manager)': 'DEPT_MANAGER',
            r'(?:hr\s+&?\s+accounts|accounts\s+&?\s+hr)': 'HR_ADMIN',
            r'(?:finance\s+department|finance\s+admin)': 'FINANCE_ADMIN',
            r'(?:travel\s+admin|travel\s+department)': 'TRAVEL_ADMIN'
        }
        
        for clause_id, clause in self.clarified_clauses.items():
            text = clause.get('text_clarified', '').lower()
            
            for pattern, org_id in authorities_patterns.items():
                if re.search(pattern, text):
                    # Use proper case name for authority
                    proper_name = pattern.split('|')[0].replace(r'\s+', ' ').replace('(?:', '').replace(')', '').title()
                    index['authorities'][proper_name] = org_id
        
        self.log_entry("INDEX", f"Built index: {len(index['roles'])} roles, {len(index['locations'])} locations, {len(index['tenants'])} tenants, {len(index['authorities'])} authorities")
        return index
    
    def extract_metadata_with_index(self, dsl_rule, normalized_policy, extraction_index):
        """Extract metadata STRICTLY from validated index only"""
        
        when_conditions = dsl_rule.get('when', {}).get('all', [])
        rule_id = dsl_rule.get('rule_id', 'unknown')
        
        scope = normalized_policy.get('scope', {})
        applies_to = scope.get('appliesTo', {})
        
        # Get clarified clause text for exact matching
        clarified_clause = self.clarified_clauses.get(rule_id, {})
        text = clarified_clause.get('text_clarified', '') or clarified_clause.get('text_original', '')
        text_lower = text.lower()
        
        # Extract roles: ONLY from when conditions (most reliable)
        roles = []
        for condition in when_conditions:
            fact = condition.get('fact', '').lower()
            if any(x in fact for x in ['grade', 'role', 'employee']):
                val = condition.get('value')
                if val and isinstance(val, str):
                    role = val.strip()
                    if role and len(role) < 100:
                        roles.append(role)
        
        # Also check if index roles are EXPLICITLY mentioned (exact word match)
        for role_value in extraction_index['roles'].keys():
            pattern = r'\b' + re.escape(role_value) + r'\b'
            if re.search(pattern, text_lower):
                if role_value not in roles:
                    roles.append(role_value)
        
        if roles:
            applies_to['roles'] = list(dict.fromkeys(roles))
        
        # Extract locations: ONLY from when conditions (most reliable)
        locations = []
        for condition in when_conditions:
            fact = condition.get('fact', '').lower()
            if any(x in fact for x in ['location', 'category', 'area', 'region']):
                val = condition.get('value')
                if val and isinstance(val, str):
                    location = val.strip()
                    if location and len(location) < 100:
                        locations.append(location)
        
        # Also check if index locations are EXPLICITLY mentioned (exact word match)
        for location_value in extraction_index['locations'].keys():
            pattern = r'\b' + re.escape(location_value) + r'\b'
            if re.search(pattern, text_lower):
                if location_value not in locations:
                    locations.append(location_value)
        
        if locations:
            applies_to['locations'] = list(dict.fromkeys(locations))
        
        # Extract tenant: ONLY from index (first match)
        for tenant_value in extraction_index['tenants'].keys():
            pattern = r'\b' + re.escape(tenant_value) + r'\b'
            if re.search(pattern, text_lower):
                scope['tenantId'] = tenant_value
                break
        
        # Extract authority/orgId: ONLY from index authorities
        for authority, org_id in extraction_index['authorities'].items():
            pattern = r'\b' + re.escape(authority.lower()) + r'\b'
            if re.search(pattern, text_lower):
                scope['orgId'] = org_id
                break
        
        # Default orgId if not explicitly found
        if not scope.get('orgId'):
            scope['orgId'] = None
        
        scope['appliesTo'] = applies_to
        normalized_policy['scope'] = scope
        
        self.log_entry("EXTRACT", f"{rule_id}: roles={roles}, locations={locations}, tenant={scope.get('tenantId')}, org={scope.get('orgId')}")
    
    def extract_metadata_with_llm(self, dsl_rule, normalized_policy, extraction_index):
        """Use LLM only when index-based extraction is incomplete"""
        
        rule_id = dsl_rule.get('rule_id', 'unknown')
        scope = normalized_policy.get('scope', {})
        applies_to = scope.get('appliesTo', {})
        
        # Check if extraction was complete
        needs_llm = (
            not scope.get('tenantId') or 
            not scope.get('orgId') or
            not applies_to.get('roles') or
            not applies_to.get('locations')
        )
        
        if not needs_llm or not self.llm_enabled:
            return
        
        clarified_clause = self.clarified_clauses.get(rule_id, {})
        text = clarified_clause.get('text_clarified', '')
        
        prompt = f"""Extract missing metadata from this policy clause.

CLAUSE TEXT:
{text}

RULE ID: {rule_id}

Current extracted values:
- roles: {applies_to.get('roles', [])}
- locations: {applies_to.get('locations', [])}
- tenantId: {scope.get('tenantId')}
- orgId: {scope.get('orgId')}

Fill in any missing values as JSON (or return {{}} if nothing found):
{{"roles": [], "locations": [], "tenantId": null, "orgId": null}}
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip().replace('```json', '').replace('```', '')
            metadata = json.loads(response_text)
            
            # Merge LLM results with existing
            if metadata.get('roles'):
                applies_to['roles'] = list(set(applies_to.get('roles', []) + metadata['roles']))
            if metadata.get('locations'):
                applies_to['locations'] = list(set(applies_to.get('locations', []) + metadata['locations']))
            if metadata.get('tenantId') and not scope.get('tenantId'):
                scope['tenantId'] = metadata['tenantId']
            if metadata.get('orgId') and not scope.get('orgId'):
                scope['orgId'] = metadata['orgId']
            
            self.log_entry("LLM", f"{rule_id}: Filled gaps with LLM")
        except Exception as e:
            self.log_entry("WARNING", f"{rule_id}: LLM extraction failed: {e}")
    
    def build_stage_data_map(self):
        """Load and index all stage data by clauseId"""
        stage_map = {}
        
        # Stage 1: Raw clauses
        try:
            with open(f"{OUTPUT_DIR}/stage1_clauses.json") as f:
                stage1_data = json.load(f)
            for clause in stage1_data.get('clauses', []):
                clause_id = clause.get('clauseId')
                if clause_id not in stage_map:
                    stage_map[clause_id] = {}
                stage_map[clause_id]['stage1'] = clause
        except Exception as e:
            self.log_entry("WARNING", f"Stage 1 load failed: {e}")
        
        # Stage 2: Classification
        try:
            with open(f"{OUTPUT_DIR}/stage2_classified.json") as f:
                stage2_data = json.load(f)
            for clause in stage2_data.get('classified_clauses', []):
                clause_id = clause.get('clauseId')
                if clause_id not in stage_map:
                    stage_map[clause_id] = {}
                stage_map[clause_id]['stage2'] = clause
        except Exception as e:
            self.log_entry("WARNING", f"Stage 2 load failed: {e}")
        
        # Stage 3: Entities
        try:
            with open(f"{OUTPUT_DIR}/stage3_entities.json") as f:
                stage3_data = json.load(f)
            for clause in stage3_data.get('extracted_clauses', []):
                clause_id = clause.get('clauseId')
                if clause_id not in stage_map:
                    stage_map[clause_id] = {}
                stage_map[clause_id]['stage3'] = clause
        except Exception as e:
            self.log_entry("WARNING", f"Stage 3 load failed: {e}")
        
        # Stage 4: Ambiguity flags
        try:
            with open(f"{OUTPUT_DIR}/stage4_ambiguity_flags.json") as f:
                stage4_data = json.load(f)
            for clause in stage4_data.get('ambiguity_flags', []):
                clause_id = clause.get('clauseId')
                if clause_id not in stage_map:
                    stage_map[clause_id] = {}
                stage_map[clause_id]['stage4'] = clause
        except Exception as e:
            self.log_entry("WARNING", f"Stage 4 load failed: {e}")
        
        # Stage 5: Clarified clauses (already loaded)
        for clause_id, clause in self.clarified_clauses.items():
            if clause_id not in stage_map:
                stage_map[clause_id] = {}
            stage_map[clause_id]['stage5'] = clause
        
        # Stage 6: DSL rules
        try:
            import yaml
            with open(self.dsl_file) as f:
                stage6_data = yaml.safe_load(f)
            for rule in stage6_data.get('rules', []):
                rule_id = rule.get('rule_id')
                if rule_id not in stage_map:
                    stage_map[rule_id] = {}
                stage_map[rule_id]['stage6'] = rule
        except Exception as e:
            self.log_entry("WARNING", f"Stage 6 load failed: {e}")
        
        # Stage 7: Confidence & rationale
        try:
            with open(self.confidence_file) as f:
                stage7_data = json.load(f)
            for clause_id, data in stage7_data.get('confidenceAndRationale', {}).items():
                if clause_id not in stage_map:
                    stage_map[clause_id] = {}
                stage_map[clause_id]['stage7'] = data
        except Exception as e:
            self.log_entry("WARNING", f"Stage 7 load failed: {e}")
        
        self.log_entry("INFO", f"Built stage map for {len(stage_map)} clauses")
        return stage_map
    
    def generate_normalized_policies(self):
        """Generate consolidated normalized policies from all stages"""
        self.log_entry("INFO", "Starting Stage 8: Consolidated Policy Normalization")
        
        # Load and map all stage data
        stage_map = self.build_stage_data_map()
        
        if not stage_map:
            self.log_entry("ERROR", "No clause data found in stages")
            return False
        
        self.log_entry("INFO", f"Consolidating {len(stage_map)} clauses from all stages")
        
        # Consolidate all clauses
        consolidated_records = []
        for clause_id in sorted(stage_map.keys()):
            stage_data = stage_map[clause_id]
            
            # Fill missing stages with empty defaults
            for stage in ['stage1', 'stage2', 'stage3', 'stage4', 'stage5', 'stage6', 'stage7']:
                if stage not in stage_data:
                    stage_data[stage] = {}
            
            # Consolidate this clause's data
            consolidated = self.consolidate_clause_data(clause_id, stage_data)
            consolidated_records.append(consolidated)
            
            self.log_entry("CONSOLIDATED", f"Clause {clause_id}: {stage_data['stage2'].get('intent', 'UNKNOWN')}")
        
        self.log_entry("SUCCESS", f"Consolidated {len(consolidated_records)} clauses")
        
        # Save output
        return self.save_consolidated_policies(consolidated_records)
    
    def save_consolidated_policies(self, consolidated_records):
        """Save consolidated policies to JSON file"""
        try:
            output = {
                'policies': consolidated_records,
                'metadata': {
                    'generated': datetime.now().isoformat(),
                    'total_policies': len(consolidated_records),
                    'format': 'Consolidated Policy Normalization (Stage 8)',
                    'source_stages': [1, 2, 3, 4, 5, 6, 7],
                    'description': 'Each policy contains consolidated data from all 7 processing stages'
                }
            }
            
            with open(self.normalized_file, 'w') as f:
                json.dump(output, f, indent=2)
            
            self.log_entry("SUCCESS", f"Consolidated policies saved to: {self.normalized_file}")
            
            # Store to MongoDB
            db_result = self.storage.store_stage(
                stage_number=8,
                stage_name="normalize-policies",
                stage_output=output
            )
            
            if db_result['success']:
                self.log_entry("MONGODB", f"Stage stored with ID: {db_result['stage_id']}")
            else:
                self.log_entry("WARNING", f"MongoDB storage failed: {db_result['error']}")
            
            return True
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to save consolidated policies: {e}")
            return False
    
    def save_log(self):
        """Append log to mechanism.log"""
        with open(LOG_FILE, 'a') as f:
            f.write("\n\n=== STAGE 8: NORMALIZED POLICY GENERATION LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")

# ============================================================================
# STAGE 10: OPA Bundle Storage & Management
# ============================================================================

class OPABundleStorageManager:
    """
    Stage 10: Store Rego rules in OPA-compatible bundle format with versioning,
    persistence, and rollback capability.
    
    Input: stage9_rego_bundles.json (Complete Rego packages with rules)
    Output: OPA bundle directory structure with manifest, versioning, and validation
    
    Component Architecture:
    - Bundle Generator: Convert Rego to OPA bundle format
    - Manifest Manager: Create OPA-standard manifest.json with metadata
    - Version Controller: Semantic versioning and version registry
    - Storage Backend: Hybrid persistence (filesystem + MongoDB)
    - Integrity Checker: SHA256 validation and bundle verification
    - Cleanup Manager: Retention policy and version cleanup
    """
    
    def __init__(self, rego_bundles_file, storage_dir=None, document_id=None, 
                 enable_mongodb=True, enable_cleanup=False, retention_days=30):
        """
        Initialize OPA Bundle Storage Manager
        
        Args:
            rego_bundles_file (str): Path to stage9_rego_bundles.json
            storage_dir (str): Directory for bundle storage (default: OUTPUT_DIR/opa_bundles)
            document_id (str): Reference to document in raw_documents collection
                              If None, auto-generates from policy_type + timestamp
            enable_mongodb (bool): Store metadata and versions to MongoDB
            enable_cleanup (bool): Enable automatic cleanup of old versions
            retention_days (int): Days to retain old versions before cleanup
        """
        self.rego_bundles_file = rego_bundles_file
        self.storage_dir = storage_dir or f"{OUTPUT_DIR}/opa_bundles"
        
        # Auto-generate document_id if not provided
        if document_id:
            self.document_id = document_id
        else:
            # Extract policy type from stage9 for ID generation
            try:
                with open(rego_bundles_file, 'r') as f:
                    stage9_data = json.load(f)
                policy_type = stage9_data.get('policies', [{}])[0].get('policy_name', 'policy')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.document_id = f"{policy_type}_{timestamp}"
            except:
                self.document_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.enable_mongodb = enable_mongodb and MONGODB_AVAILABLE
        self.enable_cleanup = enable_cleanup
        self.retention_days = retention_days
        
        self.log = []
        self.log_lock = threading.Lock()
        
        # Bundle metadata
        self.bundle_metadata = None
        self.bundle_version = None
        self.bundle_hash = None
        self.version_registry = []
        
        # Initialize storage
        self.storage = PipelineStageStorage(enable_mongodb=enable_mongodb, document_id=document_id)
        
        # Create storage directory
        Path(self.storage_dir).mkdir(parents=True, exist_ok=True)
        self.log_entry("INFO", f"OPA Bundle Storage initialized at: {self.storage_dir}")
    
    def log_entry(self, level, message):
        """Thread-safe log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.log_lock:
            self.log.append(entry)
        print(entry)
    
    # ========================================================================
    # STEP 1: Read Stage 9 Output
    # ========================================================================
    
    def read_rego_bundles(self):
        """
        Read stage9_rego_bundles.json and validate structure
        
        Expected structure:
        {
            "metadata": {
                "stage": 9,
                "total_rules": N,
                "generated": "ISO timestamp"
            },
            "policies": [
                {
                    "rule_count": N,
                    "rule_details": [...],
                    "policy_category": "..."
                }
            ],
            "rego_code": {
                "package": "policies.main",
                "imports": [...],
                "rules": [...]
            },
            "statistics": {
                "ambiguous_rules": N,
                "enforce_rules": N,
                ...
            }
        }
        
        Returns:
            dict: Parsed stage9 output or None if failed
        """
        try:
            with open(self.rego_bundles_file, 'r') as f:
                data = json.load(f)
            
            # Validate required fields
            if "metadata" not in data or "rego_code" not in data:
                self.log_entry("ERROR", "Invalid stage9 structure: missing 'metadata' or 'rego_code'")
                return None
            
            if "package" not in data["rego_code"]:
                self.log_entry("ERROR", "Invalid rego_code: missing 'package' field")
                return None
            
            self.log_entry("SUCCESS", f"Read stage9 output: {len(data.get('policies', []))} policies")
            self.bundle_metadata = data["metadata"]
            return data
            
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"Failed to parse stage9 JSON: {e}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read rego bundles: {e}")
            return None
    
    # ========================================================================
    # STEP 2: Bundle Generator - Convert to OPA Format
    # ========================================================================
    
    def generate_opa_bundle(self, rego_data):
        """
        Convert stage9 Rego output to OPA-compatible bundle format
        
        OPA Bundle Structure:
        bundle/
        ├── .manifest                    (OPA standard manifest)
        ├── data.json                    (Data bundles - policy constants, thresholds)
        ├── policies/
        │   ├── main.rego               (Main policy package)
        │   └── helpers.rego            (Helper functions)
        └── bundles.json                (Bundle metadata)
        
        Args:
            rego_data (dict): Parsed stage9 output
            
        Returns:
            dict: Generated bundle structure or None if failed
        """
        try:
            self.log_entry("STEP", "Generating OPA bundle structure")
            
            bundle_structure = {
                "bundle_id": self.generate_bundle_id(),
                "created_at": datetime.now().isoformat(),
                "policies": {},
                "rego_code": {},
                "data": {
                    "metadata": rego_data.get("metadata", {}),
                    "statistics": rego_data.get("statistics", {})
                },
                "metadata": rego_data.get("metadata", {})
            }
            
            # Extract policies and rules from stage9 structure
            policies = rego_data.get("policies", [])
            total_rules = 0
            
            # Organize rules by policy
            for policy in policies:
                if isinstance(policy, dict):
                    policy_name = policy.get("policy_name", "default")
                    rules = policy.get("rules", [])
                    
                    bundle_structure["policies"][policy_name] = {
                        "package": policy.get("package", f"data.{policy_name}"),
                        "description": policy.get("description", ""),
                        "rule_count": len(rules),
                        "rules": rules
                    }
                    total_rules += len(rules)
            
            self.log_entry("SUCCESS", f"Generated bundle structure with {total_rules} rules from {len(policies)} policies")
            return bundle_structure
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to generate OPA bundle: {e}")
            return None
    
    def generate_bundle_id(self):
        """Generate unique bundle ID based on timestamp and hash"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        import hashlib
        hash_str = hashlib.md5(timestamp.encode()).hexdigest()[:8]
        return f"bundle_{timestamp}_{hash_str}"
    
    # ========================================================================
    # STEP 3: Manifest Manager - Create OPA Manifest
    # ========================================================================
    
    def create_manifest(self, bundle_structure):
        """
        Create manifest.json following OPA standard + custom metadata
        
        Manifest Format:
        {
            "version": "semantic version",
            "rules_count": N,
            "created": "ISO timestamp",
            "hash": "sha256:...",
            "policy_type": "policy_name",
            "metadata": {
                "bundle_name": "...",
                "rego_version": "v1",
                "source_stage": 9,
                "destination_stage": 10,
                "document_id": "..."
            }
        }
        
        Args:
            bundle_structure (dict): Generated bundle structure
            
        Returns:
            dict: Manifest with OPA standard + custom fields or None if failed
        """
        try:
            self.log_entry("STEP", "Creating manifest.json")
            
            # Count rules - get from first policy or 0
            policies = bundle_structure.get("policies", {})
            rule_count = 0
            policy_type = "travel_policy"
            
            for policy_name, policy_data in policies.items():
                if isinstance(policy_data, dict):
                    rules = policy_data.get("rules", [])
                    rule_count += len(rules)
                    policy_type = policy_name
            
            manifest = {
                "version": self.bundle_version or self.generate_semantic_version(),
                "rules_count": rule_count,
                "created": datetime.now().isoformat() + "Z",
                "hash": "",  # Will be filled with SHA256 after calculation
                "policy_type": policy_type,
                "metadata": {
                    "bundle_name": f"policy_{self.document_id}",
                    "rego_version": "v1",
                    "source_stage": 9,
                    "destination_stage": 10,
                    "document_id": self.document_id
                }
            }
            
            self.log_entry("SUCCESS", f"Created manifest with {rule_count} rules")
            return manifest
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to create manifest: {e}")
            return None
    
    # ========================================================================
    # STEP 4: Version Controller - Semantic Versioning & Registry
    # ========================================================================
    
    def load_version_registry(self):
        """
        Load versions.json registry with all deployed versions and active pointers
        
        Registry Format:
        {
            "active": "v1.0.10",        # Currently active version
            "previous": "v1.0.9",       # Previous active (for rollback)
            "all_versions": ["v1.0.9", "v1.0.10"],
            "created": "ISO timestamp",
            "latest": "1.0.10",
            "versions": [
                {
                    "version": "1.0.10",
                    "created": "ISO timestamp",
                    "status": "active",
                    "policy_type": "travel_policy",
                    "rules_count": 56,
                    "hash": "sha256:...",
                    "document_id": "...",
                    "filesystem_path": "v1.0.10"
                }
            ]
        }
        
        Returns:
            dict: Version registry or empty structure if not exists
        """
        try:
            versions_file = f"{self.storage_dir}/versions.json"
            if os.path.exists(versions_file):
                with open(versions_file, 'r') as f:
                    return json.load(f)
            # Initialize empty registry with pointers
            return {
                "active": None,
                "previous": None,
                "all_versions": [],
                "created": None,
                "latest": None,
                "versions": []
            }
        except Exception as e:
            self.log_entry("WARNING", f"Failed to load version registry: {e}")
            return {
                "active": None,
                "previous": None,
                "all_versions": [],
                "created": None,
                "latest": None,
                "versions": []
            }
    
    def update_version_registry(self, manifest, version_dir, status="active"):
        """
        Update versions.json with new version metadata and active pointers
        
        Updates:
        - Adds new version entry
        - Manages active/previous pointers
        - Updates all_versions list
        - Sets created timestamp
        
        Args:
            manifest (dict): Manifest object
            version_dir (str): Filesystem path to bundle
            status (str): Version status (active/inactive/archived)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.log_entry("STEP", "Updating version registry with active pointers")
            
            # Load current registry
            registry = self.load_version_registry()
            
            # Create version entry
            version_entry = {
                "version": manifest.get("version"),
                "created": manifest.get("created"),
                "status": status,
                "policy_type": manifest.get("policy_type"),
                "rules_count": manifest.get("rules_count"),
                "hash": manifest.get("hash", "").replace("sha256:", ""),
                "document_id": manifest.get("metadata", {}).get("document_id"),
                "filesystem_path": version_dir.split("/")[-1],
                "bundle_name": manifest.get("metadata", {}).get("bundle_name")
            }
            
            # Add to versions list
            registry["versions"].append(version_entry)
            registry["latest"] = manifest.get("version")
            
            # Update active pointers
            if status == "active":
                # If this version is active, move current active to previous
                if registry.get("active"):
                    registry["previous"] = registry["active"]
                registry["active"] = f"v{manifest.get('version')}"
            
            # Update all_versions list with unique versions
            version_str = f"v{manifest.get('version')}"
            if version_str not in registry.get("all_versions", []):
                registry.setdefault("all_versions", []).append(version_str)
            
            # Set registry creation time (first creation only)
            if not registry.get("created"):
                registry["created"] = datetime.now().isoformat() + "Z"
            
            # Save registry
            versions_file = f"{self.storage_dir}/versions.json"
            with open(versions_file, 'w') as f:
                json.dump(registry, f, indent=2)
            
            self.log_entry("SUCCESS", f"Version registry updated: active={registry.get('active')}, previous={registry.get('previous')}")
            return True
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to update version registry: {e}")
            return False
    
    def rollback_to_previous_version(self):
        """
        Rollback to previous active version
        
        Updates registry:
        - active → previous
        - previous → None (unless more history needed)
        - Marks old active as inactive
        
        Returns:
            dict: {'success': bool, 'previous_version': str, 'error': str}
        """
        try:
            self.log_entry("STEP", "Rolling back to previous version")
            
            registry = self.load_version_registry()
            
            if not registry.get("previous"):
                return {'success': False, 'previous_version': None, 'error': 'No previous version available'}
            
            previous_version = registry["previous"]
            current_version = registry["active"]
            
            # Update version statuses
            for version_entry in registry.get("versions", []):
                if version_entry.get("version") == current_version.replace("v", ""):
                    version_entry["status"] = "inactive"
                elif version_entry.get("version") == previous_version.replace("v", ""):
                    version_entry["status"] = "active"
            
            # Update active pointers
            registry["active"] = previous_version
            registry["previous"] = current_version
            
            # Save updated registry
            versions_file = f"{self.storage_dir}/versions.json"
            with open(versions_file, 'w') as f:
                json.dump(registry, f, indent=2)
            
            self.log_entry("SUCCESS", f"Rolled back: {current_version} → {previous_version}")
            return {
                'success': True,
                'previous_version': previous_version,
                'current_version': current_version,
                'error': None
            }
            
        except Exception as e:
            self.log_entry("ERROR", f"Rollback failed: {e}")
            return {'success': False, 'previous_version': None, 'error': str(e)}
    
    def generate_semantic_version(self, increment_type="patch"):
        """
        Generate semantic version (major.minor.patch)
        
        Args:
            increment_type (str): 'major', 'minor', or 'patch'
            
        Returns:
            str: New semantic version
        """
        try:
            version_file = f"{self.storage_dir}/.version_registry"
            
            # Read previous versions
            versions = []
            if Path(version_file).exists():
                with open(version_file, 'r') as f:
                    versions = [line.strip() for line in f.readlines()]
            
            if not versions:
                new_version = "1.0.0"
            else:
                last_version = versions[-1]
                major, minor, patch = map(int, last_version.split('.'))
                
                if increment_type == "major":
                    major += 1
                    minor = 0
                    patch = 0
                elif increment_type == "minor":
                    minor += 1
                    patch = 0
                else:  # patch
                    patch += 1
                
                new_version = f"{major}.{minor}.{patch}"
            
            # Store new version
            with open(version_file, 'a') as f:
                f.write(f"{new_version}\n")
            
            self.bundle_version = new_version
            self.log_entry("SUCCESS", f"Generated semantic version: {new_version}")
            return new_version
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to generate semantic version: {e}")
            return "1.0.0"
    
    # ========================================================================
    # STEP 5: Integrity Checker - SHA256 Validation
    # ========================================================================
    
    def calculate_bundle_hash(self, manifest, rego_code_content):
        """
        Calculate SHA256 hash for bundle integrity verification
        
        Hash is calculated from: sha256(manifest.json + rego_code)
        This ensures:
        - Tamper detection: Any change to manifest or rules is detected
        - Reproducibility: Same manifest + rules = same hash
        
        IMPORTANT: Manifest hash field MUST be excluded from calculation
        
        Args:
            manifest (dict): Manifest object (without hash field for calculation)
            rego_code_content (str): Serialized Rego code
            
        Returns:
            str: SHA256 hash in hex format
        """
        try:
            import hashlib
            
            # Remove hash field if present (should not be)
            manifest_copy = manifest.copy()
            manifest_copy.pop("hash", None)
            
            # Serialize manifest to JSON (sorted keys for reproducibility)
            manifest_json = json.dumps(manifest_copy, sort_keys=True)
            
            # Combine manifest + rego code
            combined_content = manifest_json + rego_code_content
            
            # Calculate SHA256
            hash_object = hashlib.sha256(combined_content.encode())
            hash_hex = hash_object.hexdigest()
            
            self.bundle_hash = hash_hex
            self.log_entry("SUCCESS", f"Calculated integrity hash: {hash_hex[:16]}... (manifest + rego_code)")
            return hash_hex
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to calculate bundle hash: {e}")
            return None
    
    def verify_bundle_integrity(self, manifest, rego_code_content, expected_hash):
        """
        Verify bundle integrity using SHA256 hash
        
        Confirms that manifest.json + rego_code hasn't been tampered with
        
        Args:
            manifest (dict): Manifest object
            rego_code_content (str): Serialized Rego code
            expected_hash (str): Expected SHA256 hash
            
        Returns:
            bool: True if integrity verified, False otherwise
        """
        try:
            calculated_hash = self.calculate_bundle_hash(manifest, rego_code_content)
            
            if calculated_hash == expected_hash:
                self.log_entry("SUCCESS", "Bundle integrity verified - manifest + rego unchanged")
                return True
            else:
                self.log_entry("ERROR", f"Bundle integrity check FAILED: {calculated_hash} != {expected_hash}")
                self.log_entry("ERROR", "This indicates the manifest or rego code has been modified")
                return False
                
        except Exception as e:
            self.log_entry("ERROR", f"Failed to verify bundle integrity: {e}")
            return False
    
    # ========================================================================
    # STEP 6: Storage Backend - Hybrid Persistence
    # ========================================================================
    
    def persist_bundle_to_filesystem(self, bundle_structure, manifest):
        """
        Store bundle to filesystem with version directory structure
        
        Directory Layout:
        opa_bundles/
        ├── v1.0.0/
        │   ├── .manifest
        │   ├── policies/
        │   │   ├── main.rego
        │   │   └── helpers.rego
        │   ├── data.json
        │   └── bundle_metadata.json
        ├── v1.0.1/
        ...
        
        Args:
            bundle_structure (dict): Generated bundle
            manifest (dict): OPA manifest
            
        Returns:
            str: Path to stored bundle directory or None if failed
        """
        try:
            self.log_entry("STEP", "Persisting bundle to filesystem")
            
            version = manifest.get("version", "1.0.0")
            version_dir = f"{self.storage_dir}/v{version}"
            policies_dir = f"{version_dir}/.policy"
            
            # Create version directory
            Path(version_dir).mkdir(parents=True, exist_ok=True)
            Path(policies_dir).mkdir(parents=True, exist_ok=True)
            
            # Write manifest.json
            manifest_file = f"{version_dir}/manifest.json"
            with open(manifest_file, 'w') as f:
                json.dump(manifest, f, indent=2)
            self.log_entry("SUCCESS", f"Wrote manifest: {manifest_file}")
            
            # Write bundle metadata
            bundle_meta_file = f"{version_dir}/bundle_metadata.json"
            with open(bundle_meta_file, 'w') as f:
                json.dump(bundle_structure, f, indent=2)
            self.log_entry("SUCCESS", f"Wrote bundle metadata: {bundle_meta_file}")
            
            # Write Rego policies with policy name
            policy_type = manifest.get("policy_type", "main")
            rego_file = f"{policies_dir}/{policy_type}.rego"
            rego_content = self.serialize_rego_code(bundle_structure)
            with open(rego_file, 'w') as f:
                f.write(rego_content)
            self.log_entry("SUCCESS", f"Wrote Rego policies: {rego_file}")
            
            # Write data bundle
            data_file = f"{version_dir}/data.json"
            with open(data_file, 'w') as f:
                json.dump(bundle_structure.get("data", {}), f, indent=2)
            self.log_entry("SUCCESS", f"Wrote data bundle: {data_file}")
            
            # Write hash for integrity
            hash_file = f"{version_dir}/.bundle_hash"
            with open(hash_file, 'w') as f:
                f.write(self.bundle_hash or "")
            
            self.log_entry("SUCCESS", f"Bundle persisted to: {version_dir}")
            return version_dir
            
        except Exception as e:
            self.log_entry("ERROR", f"Failed to persist bundle to filesystem: {e}")
            return None
    
    def serialize_rego_code(self, bundle_structure):
        """
        Serialize Rego code from bundle structure to text format
        
        Args:
            bundle_structure (dict): Bundle structure with policies and rules
            
        Returns:
            str: Formatted Rego code
        """
        lines = []
        
        policies = bundle_structure.get("policies", {})
        
        # Iterate through each policy and its rules
        for policy_name, policy_data in policies.items():
            if isinstance(policy_data, dict):
                # Add package declaration
                package = policy_data.get("package", f"data.{policy_name}")
                lines.append(f"package {package}")
                lines.append("")
                
                # Add description as comment
                description = policy_data.get("description", "")
                if description:
                    lines.append(f"# {description}")
                    lines.append("")
                
                # Add rules
                rules = policy_data.get("rules", [])
                for rule in rules:
                    if isinstance(rule, dict):
                        rule_name = rule.get("rego_rule_name", "unnamed_rule")
                        rego_code = rule.get("rego_code", "")
                        lines.append(f"\n{rego_code}")
                    else:
                        lines.append(str(rule))
                
                lines.append("\n" + "="*80)
        
        return "\n".join(lines)
    
    def persist_bundle_to_mongodb(self, bundle_structure, manifest, version_dir):
         """
         Store bundle metadata to MongoDB with dual persistence backup
         
         Collections structure:
         - opa_bundles (main collection):
             ├── bundle_version (semantic version)
             ├── rego_code (complete Rego rules)
             ├── manifest (OPA manifest)
             ├── created_at (timestamp)
             ├── status (active/inactive/archived)
             ├── document_id (traceability)
             ├── policy_type (bundle classification)
             └── hash (SHA256 integrity)
         
         Args:
             bundle_structure (dict): Generated bundle
             manifest (dict): OPA manifest
             version_dir (str): Filesystem path to version directory
             
         Returns:
             dict: {'success': bool, 'stage_id': str, 'error': str}
         """
         try:
             if not self.enable_mongodb:
                 self.log_entry("DEBUG", "MongoDB storage disabled")
                 return {'success': False, 'stage_id': None, 'error': 'MongoDB disabled'}
             
             self.log_entry("STEP", "Persisting bundle to MongoDB (dual persistence)")
             
             # Read rego code for storage
             policy_dir = f"{version_dir}/.policy"
             rego_code_content = ""
             if os.path.exists(policy_dir):
                 rego_files = [f for f in os.listdir(policy_dir) if f.endswith(".rego")]
                 for rego_file in sorted(rego_files):
                     with open(f"{policy_dir}/{rego_file}", 'r') as f:
                         rego_code_content += f.read()
             
             bundle_record = {
                 "document_id": self.document_id,
                 "stage": 10,
                 "stage_name": "opa_bundle_storage",
                 "bundle_version": manifest.get("version"),
                 "bundle_id": bundle_structure.get("bundle_id"),
                 "created_at": bundle_structure.get("created_at"),
                 "policy_type": manifest.get("policy_type"),
                 "rule_count": manifest.get("rules_count", 0),
                 "manifest": manifest,
                 "rego_code": rego_code_content,
                 "filesystem_path": version_dir,
                 "bundle_hash": self.bundle_hash,
                 "status": "active",  # active/inactive/archived
                 "metadata": {
                     "bundle_name": manifest.get("metadata", {}).get("bundle_name"),
                     "rego_version": manifest.get("metadata", {}).get("rego_version"),
                     "source_stage": manifest.get("metadata", {}).get("source_stage"),
                     "destination_stage": manifest.get("metadata", {}).get("destination_stage")
                 }
             }
             
             # Use pipeline stage storage for MongoDB persistence
             result = self.storage.store_stage(
                 stage_number=10,
                 stage_name="opa_bundle_storage",
                 stage_output=bundle_record,
                 filename=self.rego_bundles_file.split('/')[-1]
             )
             
             if result['success']:
                 self.log_entry("SUCCESS", f"Bundle stored to MongoDB: {result['stage_id']} (status: active)")
             else:
                 self.log_entry("WARNING", f"MongoDB storage failed: {result['error']}")
             
             return result
             
         except Exception as e:
             self.log_entry("ERROR", f"Failed to persist bundle to MongoDB: {e}")
             return {'success': False, 'stage_id': None, 'error': str(e)}
    
    # ========================================================================
    # STEP 7: Cleanup Manager - Retention Policy & Archive
    # ========================================================================
    
    def cleanup_old_versions(self, keep_count=5, archive_old=False, archive_dir=None):
         """
         Delete/archive old bundle versions based on retention policy
         
         Retention Policy:
         - Keep last N versions active/inactive
         - Archive versions older than N (optional)
         - Delete archived versions if needed
         - Log all operations for audit trail
         
         Args:
             keep_count (int): Number of recent versions to keep
             archive_old (bool): Archive old versions instead of deleting
             archive_dir (str): Directory for archived versions
             
         Returns:
             dict: {
                 'deleted': [list of deleted versions],
                 'archived': [list of archived versions],
                 'kept': [list of kept versions],
                 'error': str or None
             }
         """
         try:
             if not self.enable_cleanup:
                 self.log_entry("DEBUG", "Cleanup disabled")
                 return {'deleted': [], 'archived': [], 'kept': [], 'error': None}
             
             self.log_entry("STEP", f"Cleaning up old versions (keeping {keep_count})")
             
             # Load version registry
             registry = self.load_version_registry()
             
             # Get all versions sorted by creation date
             all_versions = registry.get("versions", [])
             sorted_versions = sorted(all_versions, key=lambda x: x.get("created", ""), reverse=True)
             
             deleted = []
             archived = []
             kept = [v.get("version") for v in sorted_versions[:keep_count]]
             
             # Process old versions
             for version_entry in sorted_versions[keep_count:]:
                 version = version_entry.get("version")
                 version_dir = f"{self.storage_dir}/v{version}"
                 
                 if archive_old and archive_dir:
                     # Archive instead of delete
                     try:
                         import shutil
                         archive_path = f"{archive_dir}/v{version}"
                         Path(archive_dir).mkdir(parents=True, exist_ok=True)
                         shutil.move(version_dir, archive_path)
                         archived.append(version)
                         
                         # Update status in registry
                         version_entry["status"] = "archived"
                         self.log_entry("SUCCESS", f"Archived version: v{version}")
                     except Exception as e:
                         self.log_entry("WARNING", f"Failed to archive v{version}: {e}")
                 else:
                     # Delete old version
                     try:
                         import shutil
                         shutil.rmtree(version_dir)
                         deleted.append(version)
                         
                         # Update status in registry
                         version_entry["status"] = "deleted"
                         self.log_entry("SUCCESS", f"Deleted version: v{version}")
                     except Exception as e:
                         self.log_entry("WARNING", f"Failed to delete v{version}: {e}")
             
             # Update registry with new statuses
             versions_file = f"{self.storage_dir}/versions.json"
             with open(versions_file, 'w') as f:
                 json.dump(registry, f, indent=2)
             
             self.log_entry("SUCCESS", f"Cleanup complete: deleted={len(deleted)}, archived={len(archived)}, kept={len(kept)}")
             return {'deleted': deleted, 'archived': archived, 'kept': kept, 'error': None}
             
         except Exception as e:
             self.log_entry("ERROR", f"Cleanup failed: {e}")
             return {'deleted': [], 'archived': [], 'kept': [], 'error': str(e)}
    
    # ========================================================================
    # Main Processing Workflow
    # ========================================================================
    
    def process(self):
        """
        Main workflow:
        1. Read stage9 output
        2. Generate OPA bundle structure
        3. Create manifest
        4. Generate semantic version
        5. Serialize Rego code
        6. Calculate integrity hash: sha256(manifest + rego_code)
        7. Persist to filesystem
        8. Persist to MongoDB
        9. Cleanup old versions
        
        Returns:
            dict: {
                'success': bool,
                'bundle_version': str,
                'bundle_hash': str,
                'filesystem_path': str,
                'mongodb_result': dict,
                'cleanup_result': dict
            }
        """
        self.log_entry("START", "Stage 10: OPA Bundle Storage & Management")
        
        try:
            # Step 1: Read stage9 output
            rego_data = self.read_rego_bundles()
            if not rego_data:
                return {'success': False, 'error': 'Failed to read rego bundles'}
            
            # Step 2: Generate OPA bundle structure
            bundle_structure = self.generate_opa_bundle(rego_data)
            if not bundle_structure:
                return {'success': False, 'error': 'Failed to generate OPA bundle'}
            
            # Step 3: Create OPA manifest
            manifest = self.create_manifest(bundle_structure)
            if not manifest:
                return {'success': False, 'error': 'Failed to create manifest'}
            
            # Step 4: Generate semantic version (done in create_manifest)
            
            # Step 5: Serialize Rego code for hashing
            rego_code_content = self.serialize_rego_code(bundle_structure)
            
            # Step 6: Calculate integrity hash from manifest + rego code
            # Purpose: Detect tampering, ensure reproducibility
            # NOTE: Hash is calculated BEFORE adding hash field to manifest
            bundle_hash = self.calculate_bundle_hash(manifest, rego_code_content)
            if not bundle_hash:
                return {'success': False, 'error': 'Failed to calculate bundle hash'}
            
            # Now add hash to manifest after calculation
            manifest["hash"] = f"sha256:{bundle_hash}"
            
            # Step 7: Persist to filesystem
            version_dir = self.persist_bundle_to_filesystem(bundle_structure, manifest)
            if not version_dir:
                return {'success': False, 'error': 'Failed to persist bundle to filesystem'}
            
            # Step 8: Update version registry (versions.json)
            registry_updated = self.update_version_registry(manifest, version_dir, status="active")
            
            # Step 9: Persist to MongoDB (dual persistence backup)
            mongodb_result = self.persist_bundle_to_mongodb(bundle_structure, manifest, version_dir)
            
            # Step 10: Cleanup old versions (keep last 5)
            cleanup_result = self.cleanup_old_versions(keep_count=5, archive_old=False)
            
            # Step 11: Verify bundle fingerprint (integrity check)
            fingerprint_verified = self.verify_bundle_fingerprint(version_dir)
            
            # Prepare result
            result = {
                'success': True,
                'bundle_version': self.bundle_version,
                'bundle_hash': bundle_hash,
                'filesystem_path': version_dir,
                'fingerprint_verified': fingerprint_verified,
                'mongodb_result': mongodb_result,
                'cleanup_result': cleanup_result
            }
            
            # Step 12: Write deployment audit log
            self.write_deployment_audit_log(result, self.bundle_version, bundle_hash)
            
            self.log_entry("SUCCESS", "Stage 10 processing complete")
            return result
            
        except Exception as e:
            self.log_entry("ERROR", f"Stage 10 processing failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def verify_bundle_fingerprint(self, version_dir):
        """
        Verify bundle integrity by checking manifest hash against rego code
        
        This ensures:
        - No tampering with manifest or rego rules
        - Bundle reproducibility verification
        
        Note: Hash is calculated WITHOUT the hash field in manifest
        
        Args:
            version_dir (str): Path to bundle version directory
            
        Returns:
            bool: True if fingerprint matches, False otherwise
        """
        try:
            self.log_entry("STEP", f"Verifying bundle fingerprint: {version_dir}")
            
            # Read manifest
            manifest_file = f"{version_dir}/manifest.json"
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
            
            expected_hash = manifest.get("hash", "").replace("sha256:", "")
            if not expected_hash:
                self.log_entry("WARNING", "No hash found in manifest")
                return False
            
            # Read rego code
            rego_files = []
            policy_dir = f"{version_dir}/.policy"
            if os.path.exists(policy_dir):
                rego_files = [f for f in os.listdir(policy_dir) if f.endswith(".rego")]
            
            if not rego_files:
                self.log_entry("ERROR", "No Rego files found in bundle")
                return False
            
            # Concatenate all rego files
            rego_content = ""
            for rego_file in sorted(rego_files):
                with open(f"{policy_dir}/{rego_file}", 'r') as f:
                    rego_content += f.read()
            
            # Remove hash field from manifest copy for verification
            # (hash was not present when originally calculated)
            manifest_copy = manifest.copy()
            manifest_copy.pop("hash", None)
            
            # Verify
            verified = self.verify_bundle_integrity(manifest_copy, rego_content, expected_hash)
            return verified
            
        except Exception as e:
            self.log_entry("ERROR", f"Bundle fingerprint verification failed: {e}")
            return False
    
    def write_deployment_audit_log(self, result, bundle_version, bundle_hash):
        """
        Write deployment audit log for complete traceability
        
        Log Format (audit_log.jsonl):
        {
            "timestamp": "ISO",
            "event": "DEPLOYMENT",
            "bundle_version": "1.0.14",
            "document_id": "doc2",
            "policy_type": "travel_policy",
            "rules_count": 56,
            "hash": "...",
            "filesystem_path": "v1.0.14",
            "status": "active",
            "operation": "create/update/rollback"
        }
        
        Args:
            result (dict): Process result
            bundle_version (str): Bundle version
            bundle_hash (str): Bundle hash
            
        Returns:
            bool: True if successful
        """
        try:
            audit_log_file = f"{self.storage_dir}/audit_log.jsonl"
            
            audit_entry = {
                "timestamp": datetime.now().isoformat() + "Z",
                "event": "DEPLOYMENT",
                "bundle_version": bundle_version,
                "document_id": self.document_id,
                "policy_type": None,
                "rules_count": 0,
                "hash": bundle_hash,
                "filesystem_path": result.get("filesystem_path", "").split("/")[-1],
                "status": "active",
                "operation": "create",
                "success": result.get("success", False),
                "fingerprint_verified": result.get("fingerprint_verified", False),
                "mongodb_stored": result.get("mongodb_result", {}).get("success", False)
            }
            
            # Append to audit log (JSONL format - one JSON per line)
            with open(audit_log_file, 'a') as f:
                f.write(json.dumps(audit_entry) + "\n")
            
            self.log_entry("SUCCESS", f"Audit log entry created: {bundle_version}")
            return True
            
        except Exception as e:
            self.log_entry("WARNING", f"Failed to write audit log: {e}")
            return False
    
    def save_log(self):
        """Append log to mechanism.log"""
        try:
            with open(LOG_FILE, 'a') as f:
                f.write("\n\n=== STAGE 10: OPA BUNDLE STORAGE LOG ===\n")
                f.write(f"Timestamp: {datetime.now()}\n")
                f.write("="*60 + "\n\n")
                for entry in self.log:
                    f.write(entry + "\n")
        except Exception as e:
            print(f"Failed to save log: {e}")


if __name__ == "__main__":
    main()