# ============================================================================
# STAGE 0: Document Structure Analysis & Annexure Extraction (Policy-Agnostic)
# ============================================================================

import json
import re
from datetime import datetime
from pathlib import Path

# Configuration
BASE_DIR = "/home/hutech/Documents/docupolicy"
OUTPUT_DIR = f"{BASE_DIR}"


class DocumentStructureAnalyzer:
    """
    Step 0: Pre-process policy document to extract ALL sections including Annexures.

    Policy-Agnostic: Uses flexible regex patterns that work across different policy types,
    not hardcoded Travel Policy patterns.

    This stage solves the critical issue where Annexures (which contain actual
    policy rules like city classification, rates, thresholds) were never passed
    to downstream LLM stages.

    Input: filename.txt (raw policy document)
    Output: stage0_structured_document.json (all sections tagged and extracted)

    The analyzer identifies:
    - Document sections (Objective, Scope, Eligibility, etc.)
    - Annexures/Appendices with tabular data
    - Numbered clauses and rules
    - Any other policy-specific content
    """

    # Generic section headers (policy-agnostic patterns)
    SECTION_PATTERNS = [
        (r'^(objectives?|purpose|aim)[:\s]', 'objective'),
        (r'^(scope|applicability|coverage)[:\s]', 'scope'),
        (r'^(eligibility|who\s+does\s+this\s+apply)[:\s]', 'eligibility'),
        (r'^(general\s*rules?|norms?|terms?\s*and\s*conditions?)[:\s]', 'general_rules'),
        (r'^(definitions?|interpretation)[:\s]', 'definitions'),
        (r'^(rates?|entitlements?|allowances?)[:\s]', 'rates'),
        (r'^(accommodation|lodging|hotel)[:\s]', 'accommodation'),
        (r'^(transportation|travel|conveyance)[:\s]', 'transportation'),
        (r'^(food|dining|meals|da[ily]*\s*allowance)[:\s]', 'food'),
        (r'^(reimbursement|claims?)[:\s]', 'reimbursement'),
    ]

    # Generic annexure patterns (policy-agnostic)
    ANNEXURE_PATTERNS = [
        r'^(annexure|appendix|schedule|exhibit|attachment)\s*[-–]?\s*(\d+|[A-Z])[:\s]*(.*)',
        r'^(table|appendix)\s*(\d+|[A-Z])[:\s]*(.*)',
        r'^(\d+)\.\s*(annexure|appendix|schedule)',
    ]

    def __init__(self, policy_file, document_id=None):
        self.policy_file = policy_file
        self.output_file = f"{OUTPUT_DIR}/stage0_structured_document.json"
        self.document_id = document_id or Path(policy_file).stem
        self.log = []

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

    def identify_section(self, line):
        """Identify if line is a section header (policy-agnostic)"""
        line_lower = line.lower().strip()

        for pattern, section_type in self.SECTION_PATTERNS:
            if re.match(pattern, line_lower):
                # Extract section name from the line
                match = re.match(pattern, line_lower)
                section_name = match.group(1).strip()
                return section_type, section_name

        return None, None

    def identify_annexure(self, line):
        """Identify if line is an annexure header (policy-agnostic)"""
        for pattern in self.ANNEXURE_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                annexure_name = match.group(1).strip()
                annexure_num = match.group(2) if len(match.groups()) > 1 else ""
                annexure_title = match.group(3) if len(match.groups()) > 2 else ""

                full_name = f"{annexure_name} {annexure_num}".strip()
                if annexure_title:
                    full_name = f"{full_name}: {annexure_title}"

                return full_name

        return None

    def is_numbered_clause(self, line):
        """Check if line is a numbered clause (1., 2., a., b., etc.)"""
        pattern = r'^(\d+|[a-z])\s*[.)]\s+.+'
        return bool(re.match(pattern, line.strip()))

    def parse_tabular_data(self, lines):
        """Try to parse tabular data from lines"""
        # Look for lines with multiple columns (separated by tabs, pipes, or multiple spaces)
        table_data = {"headers": [], "rows": []}

        # Check if lines look like table rows
        table_lines = []
        for line in lines:
            line = line.strip()
            if not line or '\x0c' in line:
                continue

            # Skip headers
            if self.identify_section(line) or self.identify_annexure(line):
                continue

            # Check if line looks like a table row
            if re.match(r'^[\d\w]+\s+[\d\w]', line) or '|' in line or '\t' in line:
                table_lines.append(line)

        if len(table_lines) >= 2:
            # Try to identify headers (first line that's not a clause)
            headers = []
            for h_line in table_lines[:3]:
                if not self.is_numbered_clause(h_line):
                    # Check if it looks like headers
                    parts = re.split(r'\s{2,}|\t|\|', h_line)
                    if len(parts) > 1:
                        headers = [h.strip() for h in parts]
                        break

            if headers:
                table_data["headers"] = headers
                for line in table_lines:
                    if line != ' '.join(headers):
                        parts = re.split(r'\s{2,}|\t|\|', line)
                        row = [p.strip() for p in parts if p.strip()]
                        if row and len(row) == len(headers):
                            table_data["rows"].append(row)

            return table_data if table_data["rows"] else None

        return None

    def analyze_structure(self, content):
        """
        Parse policy document and identify all sections including Annexures.
        Policy-agnostic approach using flexible patterns.
        """
        lines = content.split('\n')

        document_info = {
            "title": "",
            "document_id": "",
            "effective_date": ""
        }

        sections = {}
        annexures = {}
        numbered_clauses = []

        current_section = "unclassified"
        section_buffer = []

        # Extract document header info (first few lines)
        header_lines = []
        for i, line in enumerate(lines[:15]):
            line = line.strip()
            if not line:
                continue
            header_lines.append(line)

            # First non-empty line is likely the title
            if i == 0 and not document_info["title"]:
                document_info["title"] = line

            # Look for document ID patterns
            doc_id_match = re.search(r'(HR|Pol|Policy|Ref)[/\-]?\s*\d+', line, re.IGNORECASE)
            if doc_id_match:
                document_info["document_id"] = doc_id_match.group(0)

        # Extract effective date
        date_match = re.search(
            r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
            content, re.IGNORECASE
        )
        if date_match:
            document_info["effective_date"] = date_match.group(1)

        self.log_entry("INFO", f"Document header: {document_info['title']} ({document_info['document_id']})")

        # Parse remaining content
        in_annexure = False
        annexure_name = None
        annexure_buffer = []

        for line in lines:
            line_stripped = line.strip()

            # Skip page breaks and empty lines
            if '\x0c' in line_stripped or not line_stripped:
                continue

            # Check for annexure headers
            annexure_match = self.identify_annexure(line_stripped)
            if annexure_match:
                # Save previous annexure content
                if in_annexure and annexure_name and annexure_buffer:
                    annexures[annexure_name] = self._parse_annexure(annexure_name, annexure_buffer)

                # Start new annexure
                annexure_name = annexure_match
                in_annexure = True
                annexure_buffer = []
                current_section = None
                continue

            # If we're in an annexure, collect content
            if in_annexure:
                annexure_buffer.append(line_stripped)
                continue

            # Check for section headers
            section_type, section_name = self.identify_section(line_stripped)
            if section_type:
                # Save previous section
                if section_buffer:
                    sections[current_section] = '\n'.join(section_buffer)

                current_section = section_type
                section_buffer = []
                continue

            # Check for numbered clauses
            if self.is_numbered_clause(line_stripped):
                clause_num = re.match(r'^(\d+|[a-z])', line_stripped).group(1)
                clause_text = re.sub(r'^(\d+|[a-z])\s*[.)]\s+', '', line_stripped)

                numbered_clauses.append({
                    "clauseId": f"C{clause_num}" if clause_num.isdigit() else f"C{clause_num}",
                    "text": clause_text,
                    "section": current_section
                })
                continue

            # Add to current section
            section_buffer.append(line_stripped)

        # Save final annexure
        if in_annexure and annexure_name and annexure_buffer:
            annexures[annexure_name] = self._parse_annexure(annexure_name, annexure_buffer)

        # Save final section
        if section_buffer:
            sections[current_section] = '\n'.join(section_buffer)

        return {
            "metadata": document_info,
            "sections": sections,
            "annexures": annexures,
            "numbered_clauses": numbered_clauses
        }

    def _parse_annexure(self, annexure_name, lines):
        """Parse annexure content (policy-agnostic)"""
        content = '\n'.join(lines)

        # Try to parse tabular data
        table_data = self.parse_tabular_data(lines)

        if table_data:
            return {
                "content": content,
                "type": "tabular",
                "parsed_data": table_data
            }

        # Try to identify annexure type
        annexure_lower = annexure_name.lower()
        content_lower = content.lower()

        annexure_type = "reference"
        parsed_data = {"content": content}

        # Check for common annexure types
        if any(x in annexure_lower for x in ['city', 'classification', 'town']):
            annexure_type = "city_classification"
            parsed_data = self._parse_city_classification(lines)
        elif any(x in annexure_lower for x in ['rate', 'allowance', 'amount', 'limit']):
            annexure_type = "rates_table"
            parsed_data = self._parse_rates_table(lines)
        elif any(x in annexure_lower for x in ['eligibility', 'criteria', 'condition']):
            annexure_type = "eligibility_rules"
            parsed_data = self._parse_rules(lines)
        elif any(x in annexure_lower for x in ['vehicle', 'car', 'transport']):
            annexure_type = "vehicle_policy"
            parsed_data = self._parse_rules(lines)
        elif any(x in annexure_lower for x in ['lodging', 'hotel', 'accommodation']):
            annexure_type = "accommodation_rates"
            parsed_data = self._parse_rates_table(lines)

        return {
            "content": content,
            "type": annexure_type,
            "parsed_data": parsed_data
        }

    def _parse_city_classification(self, lines):
        """Parse city classification data"""
        city_data = {"categories": {}}
        current_category = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for category headers
            category_match = re.match(
                r'^(Metros?|State\s*Capital|Hill\s*Stations?|District\s*HQs?|Other\s*Towns?|Tier\s*[123])[:\s-]*',
                line, re.IGNORECASE
            )
            if category_match:
                current_category = category_match.group(1).title()
                city_data["categories"][current_category] = []
                # Extract cities from the line
                city_part = line[category_match.end():].strip(':- ')
                if city_part:
                    cities = [c.strip() for c in city_part.split(',') if c.strip()]
                    city_data["categories"][current_category].extend(cities)
                continue

            # Extract cities from list lines
            if current_category:
                cities = [c.strip() for c in line.split(',') if c.strip()]
                city_data["categories"][current_category].extend(cities)

        return city_data

    def _parse_rates_table(self, lines):
        """Parse rates/amounts table"""
        rates = {"items": []}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for patterns like "Metro: 5000" or "Tier 1 - Rs. 5000"
            rate_match = re.match(r'([A-Za-z\s]+)[:\s-]+Rs?\.?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', line)
            if rate_match:
                item = rate_match.group(1).strip()
                amount = rate_match.group(2).strip()
                rates["items"].append({"item": item, "amount": amount})

        return rates

    def _parse_rules(self, lines):
        """Parse rules from lines"""
        rules = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for numbered rules
            rule_match = re.match(r'^(\d+|[a-z])\s*[.)]\s+(.+)', line)
            if rule_match:
                rules.append(line)
            # Check for bullet points
            elif line.startswith('•') or line.startswith('-'):
                rules.append(line)

        return {"rules": rules}

    def generate_all_clauses(self, structure):
        """Generate comprehensive clause list for downstream processing"""
        all_clauses = []

        # Add objective as context clause
        if structure["sections"].get("objective"):
            all_clauses.append({
                "clauseId": "C0_Objective",
                "text": structure["sections"]["objective"],
                "source": "objective",
                "clause_type": "section_header"
            })

        # Add scope as context clause
        if structure["sections"].get("scope"):
            all_clauses.append({
                "clauseId": "C0_Scope",
                "text": structure["sections"]["scope"],
                "source": "scope",
                "clause_type": "section_header"
            })

        # Add numbered clauses
        for clause in structure.get("numbered_clauses", []):
            all_clauses.append({
                "clauseId": clause["clauseId"],
                "text": clause["text"],
                "source": clause.get("section", "general"),
                "clause_type": "numbered"
            })

        # Add Annexure clauses
        for annexure_name, annexure_data in structure.get("annexures", {}).items():
            parsed = annexure_data.get("parsed_data", {})
            annexure_type = annexure_data.get("type", "reference")

            if annexure_type == "tabular" and "rows" in parsed:
                # Add table rows as clauses
                headers = parsed.get("headers", [])
                for i, row in enumerate(parsed["rows"], 1):
                    row_text = " | ".join(str(r) for r in row)
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ', '')}_Row{i}",
                        "text": row_text,
                        "source": annexure_name,
                        "clause_type": "annexure_table_row",
                        "headers": headers
                    })

            elif annexure_type == "city_classification" and "categories" in parsed:
                # Add city categories as clauses
                for category, cities in parsed["categories"].items():
                    if cities:
                        all_clauses.append({
                            "clauseId": f"CA_{annexure_name.replace(' ', '')}_{category.replace(' ', '')}",
                            "text": f"{category}: {', '.join(cities)}",
                            "source": annexure_name,
                            "clause_type": "city_classification",
                            "category": category,
                            "cities": cities
                        })

            elif annexure_type == "rates_table" and "items" in parsed:
                # Add rate items as clauses
                for i, item in enumerate(parsed["items"], 1):
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ', '')}_Rate{i}",
                        "text": f"{item['item']}: {item['amount']}",
                        "source": annexure_name,
                        "clause_type": "rate_item"
                    })

            elif "rules" in parsed:
                # Add rules as clauses
                for i, rule in enumerate(parsed["rules"], 1):
                    all_clauses.append({
                        "clauseId": f"CA_{annexure_name.replace(' ', '')}_Rule{i}",
                        "text": rule,
                        "source": annexure_name,
                        "clause_type": "annexure_rule"
                    })

            else:
                # Generic annexure content
                content = annexure_data.get("content", "")
                all_clauses.append({
                    "clauseId": f"CA_{annexure_name.replace(' ', '')}_1",
                    "text": content[:500],
                    "source": annexure_name,
                    "clause_type": "annexure"
                })

        return all_clauses

    def analyze(self):
        """
        Main method: Pre-process policy document and extract ALL sections.
        Uses policy-agnostic structure analysis.

        Returns:
            dict: Structured document with all sections, annexures, and clauses
        """
        self.log_entry("START", "Stage 0: Document Structure Analysis (Policy-Agnostic)")

        # Read raw policy text
        content = self.read_policy_text()
        if not content:
            return None

        # Parse document structure
        structure = self.analyze_structure(content)

        # Generate comprehensive clause list
        all_clauses = self.generate_all_clauses(structure)

        structure["all_clauses"] = all_clauses
        structure["metadata"]["total_clauses"] = len(all_clauses)
        structure["metadata"]["total_annexures"] = len(structure.get("annexures", {}))

        # Save structured document
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)

            self.log_entry("SUCCESS", f"Structured document saved: {self.output_file}")

        except Exception as e:
            self.log_entry("ERROR", f"Failed to save structured document: {e}")

        # Summary
        self.log_entry("SUMMARY", f"Document: {structure['metadata'].get('title', 'Unknown')}")
        self.log_entry("SUMMARY", f"Total clauses extracted: {len(all_clauses)}")
        self.log_entry("SUMMARY", f"Annexures found: {len(structure.get('annexures', {}))}")

        for annexure_name, annexure_data in structure.get("annexures", {}).items():
            self.log_entry("SUMMARY", f"  - {annexure_name}: {annexure_data.get('type', 'unknown')}")

        return structure

    def save_log(self):
        """Append discovery log to mechanism.log"""
        log_file = f"{OUTPUT_DIR}/mechanism.log"
        with open(log_file, 'a') as f:
            f.write("\n\n=== STAGE 0: DOCUMENT STRUCTURE ANALYSIS LOG ===\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            for entry in self.log:
                f.write(entry + "\n")


def main():
    """Main entry point for Stage 0"""
    import sys

    if len(sys.argv) < 2:
        policy_file = "filename.txt"
    else:
        policy_file = sys.argv[1]

    print("=" * 70)
    print("STAGE 0: Document Structure Analysis (Policy-Agnostic)")
    print("=" * 70)

    analyzer = DocumentStructureAnalyzer(policy_file)
    result = analyzer.analyze()

    if result:
        print("\n" + "=" * 70)
        print("STAGE 0 COMPLETE")
        print("=" * 70)
        print(f"Document: {result['metadata'].get('title', 'Unknown')}")
        print(f"Total clauses: {result['metadata'].get('total_clauses', 0)}")
        print(f"Annexures found: {result['metadata'].get('total_annexures', 0)}")
        print(f"Output: stage0_structured_document.json")
        print("=" * 70)

        # Save log
        analyzer.save_log()
    else:
        print("ERROR: Stage 0 analysis failed")


if __name__ == "__main__":
    main()
