"""
Pipeline Orchestrator - Manages async pipeline execution
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates async pipeline execution with progress tracking"""
    
    def __init__(self, document_id, db_manager):
        self.document_id = document_id
        self.db_manager = db_manager
        self.status = 'initializing'
        self.current_stage = 0
        self.total_stages = 8
        self.stages_results = []
        self.error = None
        self.progress = 0
        self.start_time = None
        self.end_time = None
        self.OUTPUT_DIR = "/home/hutech/Documents/docupolicy"
        
        # Import policy validator classes
        sys.path.insert(0, '/home/hutech/Documents/docupolicy')
        try:
            from policy_validator import (
                ClauseExtractor,
                IntentClassifier,
                EntityExtractor,
                AmbiguityDetector,
                AmbiguityClarifier,
                DSLGenerator,
                ConfidenceAndRationaleGenerator,
                NormalizedPolicyGenerator
            )
            self.ClauseExtractor = ClauseExtractor
            self.IntentClassifier = IntentClassifier
            self.EntityExtractor = EntityExtractor
            self.AmbiguityDetector = AmbiguityDetector
            self.AmbiguityClarifier = AmbiguityClarifier
            self.DSLGenerator = DSLGenerator
            self.ConfidenceAndRationaleGenerator = ConfidenceAndRationaleGenerator
            self.NormalizedPolicyGenerator = NormalizedPolicyGenerator
        except Exception as e:
            self.error = f"Failed to import validators: {str(e)}"
            logger.error(self.error)
    
    def log_progress(self, message):
        """Log progress message"""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{self.document_id}] {message}"
        print(log_msg)
        logger.info(log_msg)
    
    async def run(self):
        """Run the complete 7-stage pipeline asynchronously"""
        
        self.start_time = time.time()
        self.log_progress("Pipeline starting...")
        
        try:
            # Retrieve document from MongoDB
            doc = self.db_manager.get_document(self.document_id)
            if not doc:
                self.error = f"Document not found in MongoDB: {self.document_id}"
                self.status = 'failed'
                self.log_progress(f"ERROR: {self.error}")
                return False
            
            self.log_progress(f"✓ Retrieved document: {doc['filename']}")
            
            # Save content to temp file
            temp_policy_file = f"/tmp/policy_{self.document_id}.txt"
            with open(temp_policy_file, 'w') as f:
                f.write(doc['content'])
            
            self.log_progress(f"✓ Created temp file: {temp_policy_file}")
            
            # Stage 1: Extract Clauses
            if not await self._run_stage_1(temp_policy_file):
                return False
            
            # Stage 2: Classify Intent
            if not await self._run_stage_2():
                return False
            
            # Stage 3: Extract Entities
            if not await self._run_stage_3():
                return False
            
            # Stage 4: Detect Ambiguities
            if not await self._run_stage_4():
                return False
            
            # Stage 5: Clarify Ambiguities
            if not await self._run_stage_5():
                return False
            
            # Stage 6: Generate DSL Rules
            if not await self._run_stage_6():
                return False
            
            # Stage 7: Confidence & Rationale
            if not await self._run_stage_7():
                return False
            
            # Stage 8: Normalized Policies
            if not await self._run_stage_8():
                return False
            
            # Cleanup
            try:
                os.remove(temp_policy_file)
            except:
                pass
            
            self.end_time = time.time()
            self.status = 'completed'
            self.progress = 100
            total_time = self.end_time - self.start_time
            
            self.log_progress(f"✓ PIPELINE COMPLETE in {total_time:.2f}s")
            self.log_progress(f"✓ All {len(self.stages_results)} stages completed successfully")
            self.log_progress("✓ Next step: Approve policies at /approval")
            
            return True
            
        except Exception as e:
            self.error = f"Pipeline exception: {str(e)}"
            self.status = 'failed'
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_1(self, temp_policy_file):
        """Run Stage 1: Extract Clauses"""
        self.current_stage = 1
        self.progress = 14
        
        try:
            self.log_progress("Stage 1: Extracting clauses...")
            
            stage1 = self.ClauseExtractor(
                policy_file=temp_policy_file,
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            success = stage1.extract()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage1_clauses.json", 'r') as f:
                    stage1_output = json.load(f)
                
                stage1_id = self._extract_stage_id(stage1.log)
                total_clauses = len(stage1_output.get('clauses', []))
                
                self.stages_results.append({
                    'stage_number': 1,
                    'stage_name': 'extract-clauses',
                    'stage_id': stage1_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_clauses': total_clauses}
                })
                
                self.log_progress(f"✓ Stage 1 completed: {stage1_id} ({total_clauses} clauses)")
                return True
            else:
                self.error = "Stage 1 (Extract Clauses) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 1 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_2(self):
        """Run Stage 2: Classify Intent"""
        self.current_stage = 2
        self.progress = 28
        
        try:
            self.log_progress("Stage 2: Classifying intents...")
            
            stage2 = self.IntentClassifier(
                clauses_file=f"{self.OUTPUT_DIR}/stage1_clauses.json",
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            success = stage2.classify()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage2_classified.json", 'r') as f:
                    stage2_output = json.load(f)
                
                stage2_id = self._extract_stage_id(stage2.log)
                total_classified = len(stage2_output.get('classified_clauses', []))
                
                self.stages_results.append({
                    'stage_number': 2,
                    'stage_name': 'classify-intents',
                    'stage_id': stage2_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_classified': total_classified}
                })
                
                self.log_progress(f"✓ Stage 2 completed: {stage2_id} ({total_classified} classified)")
                return True
            else:
                self.error = "Stage 2 (Classify Intent) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 2 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_3(self):
        """Run Stage 3: Extract Entities"""
        self.current_stage = 3
        self.progress = 42
        
        try:
            self.log_progress("Stage 3: Extracting entities...")
            
            stage3 = self.EntityExtractor(
                classified_file=f"{self.OUTPUT_DIR}/stage2_classified.json",
                document_id=self.document_id,
                enable_mongodb=True,
                use_langchain=False,  # Use rule-based extraction (simpler)
                max_workers=8  # Parallel processing with 8 workers
            )
            
            success = stage3.extract()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage3_entities.json", 'r') as f:
                    stage3_output = json.load(f)
                
                stage3_id = self._extract_stage_id(stage3.log)
                total_entities = len(stage3_output.get('entities_extracted', []))
                
                self.stages_results.append({
                    'stage_number': 3,
                    'stage_name': 'extract-entities',
                    'stage_id': stage3_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_entities': total_entities}
                })
                
                self.log_progress(f"✓ Stage 3 completed: {stage3_id} ({total_entities} entities)")
                return True
            else:
                self.error = "Stage 3 (Extract Entities) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 3 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_4(self):
        """Run Stage 4: Detect Ambiguities"""
        self.current_stage = 4
        self.progress = 56
        
        try:
            self.log_progress("Stage 4: Detecting ambiguities...")
            
            stage4 = self.AmbiguityDetector(
                stage3_file=f"{self.OUTPUT_DIR}/stage3_entities.json",
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            success = stage4.detect_ambiguities()
            
            if success:
                # Read the saved ambiguity flags from file
                with open(f"{self.OUTPUT_DIR}/stage4_ambiguity_flags.json", 'r') as f:
                    ambiguity_flags = json.load(f)
                
                stage4_id = self._extract_stage_id(stage4.log)
                
                self.stages_results.append({
                    'stage_number': 4,
                    'stage_name': 'detect-ambiguities',
                    'stage_id': stage4_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_analyzed': len(ambiguity_flags)}
                })
                
                self.log_progress(f"✓ Stage 4 completed: {stage4_id} ({len(ambiguity_flags)} analyzed)")
                return True
            else:
                self.error = "Stage 4 (Detect Ambiguities) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 4 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_5(self):
        """Run Stage 5: Clarify Ambiguities"""
        self.current_stage = 5
        self.progress = 70
        
        try:
            self.log_progress("Stage 5: Clarifying ambiguities...")
            
            stage5 = self.AmbiguityClarifier(
                stage3_file=f"{self.OUTPUT_DIR}/stage3_entities.json",
                stage4_file=f"{self.OUTPUT_DIR}/stage4_ambiguity_flags.json",
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            success = stage5.clarify_all_clauses()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage5_clarified_clauses.json", 'r') as f:
                    stage5_output = json.load(f)
                
                stage5_id = self._extract_stage_id(stage5.log)
                total_clarified = len(stage5_output.get('clarified_clauses', []))
                
                self.stages_results.append({
                    'stage_number': 5,
                    'stage_name': 'clarify-ambiguities',
                    'stage_id': stage5_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_clarified': total_clarified}
                })
                
                self.log_progress(f"✓ Stage 5 completed: {stage5_id} ({total_clarified} clarified)")
                return True
            else:
                self.error = "Stage 5 (Clarify Ambiguities) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 5 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_6(self):
        """Run Stage 6: Generate DSL Rules"""
        self.current_stage = 6
        self.progress = 84
        
        try:
            self.log_progress("Stage 6: Generating DSL rules...")
            
            stage6 = self.DSLGenerator(
                stage5_file=f"{self.OUTPUT_DIR}/stage5_clarified_clauses.json",
                stage4_file=f"{self.OUTPUT_DIR}/stage4_ambiguity_flags.json",
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            success = stage6.generate_dsl_rules()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage6_dsl_rules.yaml", 'r') as f:
                    stage6_output = f.read()
                
                stage6_id = self._extract_stage_id(stage6.log)
                
                self.stages_results.append({
                    'stage_number': 6,
                    'stage_name': 'generate-dsl',
                    'stage_id': stage6_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'output_size': len(stage6_output)}
                })
                
                self.log_progress(f"✓ Stage 6 completed: {stage6_id}")
                return True
            else:
                self.error = "Stage 6 (Generate DSL) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 6 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_7(self):
        """Run Stage 7: Confidence & Rationale"""
        self.current_stage = 7
        self.progress = 98
        
        try:
            self.log_progress("Stage 7: Generating confidence & rationale...")
            
            stage7 = self.ConfidenceAndRationaleGenerator(
                stage5_file=f"{self.OUTPUT_DIR}/stage5_clarified_clauses.json",
                stage6_file=f"{self.OUTPUT_DIR}/stage6_dsl_rules.yaml",
                document_id=self.document_id,
                enable_mongodb=True
            )
            
            confidence_data = stage7.generate_confidence_and_rationale()
            
            if confidence_data:
                success = stage7.save_confidence_rationale(confidence_data)
                
                if success:
                    stage7_id = self._extract_stage_id(stage7.log)
                    
                    self.stages_results.append({
                        'stage_number': 7,
                        'stage_name': 'confidence-rationale',
                        'stage_id': stage7_id or 'unknown',
                        'status': 'pending_approval',
                        'created_at': datetime.utcnow().isoformat(),
                        'output_summary': {'total_rationales': len(confidence_data)}
                    })
                    
                    self.log_progress(f"✓ Stage 7 completed: {stage7_id}")
                    return True
                else:
                    self.error = "Stage 7 (Save Confidence) failed"
                    self.log_progress(f"ERROR: {self.error}")
                    return False
            else:
                self.error = "Stage 7 (Generate Confidence) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 7 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    async def _run_stage_8(self):
        """Run Stage 8: Generate Normalized Policies"""
        self.current_stage = 8
        self.progress = 99
        
        try:
            self.log_progress("Stage 8: Generating normalized policies...")
            
            stage8 = self.NormalizedPolicyGenerator(
                dsl_file=f"{self.OUTPUT_DIR}/stage6_dsl_rules.yaml",
                confidence_file=f"{self.OUTPUT_DIR}/stage7_confidence_rationale.json",
                document_id=self.document_id,
                enable_mongodb=True,
                use_langchain=False  # Fast rule-based mode
            )
            
            success = stage8.generate_normalized_policies()
            
            if success:
                with open(f"{self.OUTPUT_DIR}/stage8_normalized_policies.json", 'r') as f:
                    stage8_output = json.load(f)
                
                stage8_id = self._extract_stage_id(stage8.log)
                total_policies = len(stage8_output.get('policies', []))
                
                self.stages_results.append({
                    'stage_number': 8,
                    'stage_name': 'generate-normalized-policies',
                    'stage_id': stage8_id or 'unknown',
                    'status': 'pending_approval',
                    'created_at': datetime.utcnow().isoformat(),
                    'output_summary': {'total_policies': total_policies}
                })
                
                self.log_progress(f"✓ Stage 8 completed: {stage8_id} ({total_policies} policies normalized)")
                return True
            else:
                self.error = "Stage 8 (Generate Normalized Policies) failed"
                self.log_progress(f"ERROR: {self.error}")
                return False
                
        except Exception as e:
            self.error = f"Stage 8 exception: {str(e)}"
            self.log_progress(f"ERROR: {self.error}")
            return False
    
    def _extract_stage_id(self, log_lines):
        """Extract stage_id from log"""
        import re
        for log_line in reversed(log_lines):
            if "stage_" in log_line:
                match = re.search(r'stage_\d+_[a-f0-9]+', log_line)
                if match:
                    return match.group(0)
        return None
    
    def get_status(self):
        """Get current pipeline status"""
        return {
            'document_id': self.document_id,
            'status': self.status,
            'current_stage': self.current_stage,
            'total_stages': self.total_stages,
            'progress': self.progress,
            'stages_completed': len(self.stages_results),
            'error': self.error,
            'elapsed_time': round(time.time() - self.start_time, 2) if self.start_time else 0
        }


# Global pipeline tracker (simple in-memory storage)
_pipelines = {}


def get_or_create_pipeline(document_id, db_manager):
    """Get existing pipeline or create new one"""
    if document_id not in _pipelines:
        _pipelines[document_id] = PipelineOrchestrator(document_id, db_manager)
    return _pipelines[document_id]


def get_pipeline_status(document_id):
    """Get pipeline status"""
    if document_id in _pipelines:
        return _pipelines[document_id].get_status()
    return None
