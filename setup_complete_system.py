#!/usr/bin/env python3
"""
Complete setup script for custom search engine with your prompts
Handles database setup, data ingestion, batch classification, and search engine initialization
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any
import json
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('setup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'obsidian_vault_path': Path('/home/bao/Documents/Obsidian/Main-Vault'),
    'prompts_path': Path('/home/bao/Documents/Obsidian/Main-Vault/Areas/AI/Prompts'),
    'base_db_path': Path('/home/bao/Documents/Obsidian/Main-Vault/Bases/Prompt Database.base'),

    'db_config': {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''  # Update if you set a password
    },

    'search_strategy': 'annoy',  # 'annoy', 'multi_index', or 'hybrid'

    'batch_classification': {
        'enabled': True,
        'batch_size': 10,
        'max_concurrent': 3,
        'anthropic_api_key': None  # Set this if you want batch classification
    }
}

class CompleteSystemSetup:
    """Complete setup orchestrator for the entire system"""

    def __init__(self, config: Dict):
        self.config = config
        self.setup_steps = [
            ('check_dependencies', 'Checking dependencies'),
            ('setup_database', 'Setting up PostgreSQL database'),
            ('load_prompts', 'Loading prompts from Obsidian'),
            ('batch_classify', 'Running batch classification (optional)'),
            ('initialize_search', 'Initializing search engine'),
            ('test_system', 'Testing complete system'),
            ('save_indices', 'Saving search indices')
        ]

    async def run_complete_setup(self):
        """Run the complete setup process"""
        logger.info("="*60)
        logger.info("PROMPT FLOW COMPLETE SYSTEM SETUP")
        logger.info("="*60)

        start_time = time.time()

        try:
            for step_func, step_desc in self.setup_steps:
                logger.info(f"\n🔄 {step_desc}...")
                step_start = time.time()

                success = await getattr(self, step_func)()

                step_time = time.time() - step_start
                if success:
                    logger.info(f"✅ {step_desc} completed in {step_time:.2f}s")
                else:
                    logger.error(f"❌ {step_desc} failed!")
                    return False

            total_time = time.time() - start_time
            logger.info(f"\n🎉 Complete system setup finished in {total_time:.2f}s")
            logger.info("System is ready for use!")

            # Show quick usage example
            self.show_usage_example()

            return True

        except Exception as e:
            logger.error(f"Setup failed with error: {e}")
            return False

    async def check_dependencies(self) -> bool:
        """Check and install required dependencies"""
        required_packages = [
            'psycopg2-binary', 'sentence-transformers', 'annoy',
            'networkx', 'scikit-learn', 'spacy', 'anthropic'
        ]

        missing_packages = []

        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
            except ImportError:
                missing_packages.append(package)

        if missing_packages:
            logger.warning(f"Missing packages: {missing_packages}")
            logger.info("Please install missing packages with:")
            logger.info(f"pip install {' '.join(missing_packages)}")

            # Try to install automatically
            try:
                import subprocess
                cmd = [sys.executable, '-m', 'pip', 'install'] + missing_packages
                subprocess.run(cmd, check=True)
                logger.info("✅ Packages installed successfully")
            except Exception as e:
                logger.error(f"Failed to auto-install packages: {e}")
                return False

        # Check spacy model
        try:
            import spacy
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.info("Downloading spaCy model...")
            try:
                import subprocess
                subprocess.run([sys.executable, '-m', 'spacy', 'download', 'en_core_web_sm'], check=True)
            except Exception as e:
                logger.error(f"Failed to download spaCy model: {e}")
                return False

        logger.info("All dependencies are available")
        return True

    async def setup_database(self) -> bool:
        """Set up PostgreSQL database and schema"""
        try:
            # Import and run database setup
            from setup_database import main as setup_db_main

            # Check if prompts path exists
            if not self.config['prompts_path'].exists():
                logger.error(f"Prompts path does not exist: {self.config['prompts_path']}")
                logger.info("Please check your Obsidian vault path in CONFIG")
                return False

            # Run database setup
            logger.info(f"Setting up database with prompts from: {self.config['prompts_path']}")

            # Update the setup_database paths temporarily
            import setup_database
            original_prompts_path = setup_database.PROMPTS_PATH
            original_db_config = setup_database.DB_CONFIG

            setup_database.PROMPTS_PATH = self.config['prompts_path']
            setup_database.DB_CONFIG = self.config['db_config']

            try:
                setup_db_main()
                logger.info("Database setup completed")
            finally:
                # Restore original values
                setup_database.PROMPTS_PATH = original_prompts_path
                setup_database.DB_CONFIG = original_db_config

            return True

        except Exception as e:
            logger.error(f"Database setup failed: {e}")
            return False

    async def load_prompts(self) -> bool:
        """Verify prompts were loaded correctly"""
        try:
            import psycopg2

            conn = psycopg2.connect(**self.config['db_config'])
            cursor = conn.cursor()

            # Check prompt count
            cursor.execute("SELECT COUNT(*) FROM prompts")
            total_prompts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM prompts WHERE backfill_status = 'pending'")
            pending_classification = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM prompts WHERE array_length(intent, 1) > 0")
            has_intent = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            logger.info(f"Total prompts loaded: {total_prompts}")
            logger.info(f"Prompts needing classification: {pending_classification}")
            logger.info(f"Prompts with intent metadata: {has_intent}")

            if total_prompts == 0:
                logger.error("No prompts were loaded from the database")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to verify prompts: {e}")
            return False

    async def batch_classify(self) -> bool:
        """Run batch classification if enabled and API key available"""
        if not self.config['batch_classification']['enabled']:
            logger.info("Batch classification disabled, skipping...")
            return True

        api_key = self.config['batch_classification'].get('anthropic_api_key')
        if not api_key:
            # Try to get from environment
            api_key = os.getenv('ANTHROPIC_API_KEY')

        if not api_key:
            logger.warning("No Anthropic API key provided, skipping batch classification")
            logger.info("You can run classification later with a proper API key")
            return True

        try:
            # Run batch classification
            from batch_classify_prompts import BatchClassifier

            classifier = BatchClassifier(
                db_config=self.config['db_config'],
                api_key=api_key,
                batch_size=self.config['batch_classification']['batch_size'],
                max_concurrent=self.config['batch_classification']['max_concurrent']
            )

            # Get prompts needing classification
            prompts_to_classify = await classifier.get_pending_prompts()

            if not prompts_to_classify:
                logger.info("No prompts need classification")
                return True

            logger.info(f"Classifying {len(prompts_to_classify)} prompts...")

            # Run classification
            results = await classifier.process_all_prompts()

            logger.info(f"Classification completed: {results['successful']}/{results['total']} successful")

            if results['failed'] > 0:
                logger.warning(f"{results['failed']} prompts failed classification")

            return True

        except Exception as e:
            logger.error(f"Batch classification failed: {e}")
            logger.info("System will continue with existing metadata")
            return True  # Non-critical failure

    async def initialize_search(self) -> bool:
        """Initialize the search engine"""
        try:
            from custom_search_engine_updated import CustomSearchEngine

            logger.info(f"Initializing search engine with strategy: {self.config['search_strategy']}")

            # Create search engine
            self.search_engine = CustomSearchEngine(
                db_config=self.config['db_config'],
                vector_strategy=self.config['search_strategy']
            )

            # Initialize with your prompts
            await self.search_engine.initialize()

            logger.info("Search engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Search engine initialization failed: {e}")
            return False

    async def test_system(self) -> bool:
        """Test the complete system with sample queries"""
        try:
            test_queries = [
                "Create a marketing strategy for a new product",
                "Help me write better prompts",
                "Analyze competitor data",
                "Plan a project timeline",
                "Improve my writing skills"
            ]

            logger.info("Testing system with sample queries...")

            for i, query in enumerate(test_queries, 1):
                logger.info(f"Test {i}/5: '{query}'")

                search_params = {
                    'k': 5,
                    'domains': ['business', 'AI', 'personal'],
                    'expand_graph': True
                }

                start_time = time.time()
                results = await self.search_engine.search(query, search_params)
                search_time = time.time() - start_time

                logger.info(f"  Found {len(results)} results in {search_time:.3f}s")

                if results:
                    top_result = results[0]
                    logger.info(f"  Top result: {top_result.prompt_id} (score: {top_result.score:.3f})")
                else:
                    logger.warning(f"  No results found for query: {query}")

            logger.info("System testing completed successfully")
            return True

        except Exception as e:
            logger.error(f"System testing failed: {e}")
            return False

    async def save_indices(self) -> bool:
        """Save search indices for faster startup"""
        try:
            index_path = Path("search_indices")
            index_path.mkdir(exist_ok=True)

            base_filepath = str(index_path / "prompt_flow_indices")

            logger.info(f"Saving search indices to: {base_filepath}")
            self.search_engine.save_indices(base_filepath)

            # Save configuration
            config_path = index_path / "config.json"
            with open(config_path, 'w') as f:
                json.dump({
                    'search_strategy': self.config['search_strategy'],
                    'total_prompts': len(self.search_engine.metadata_cache),
                    'created_at': time.time()
                }, f, indent=2)

            logger.info("Search indices saved successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to save indices: {e}")
            return False

    def show_usage_example(self):
        """Show usage example"""
        logger.info("\n" + "="*60)
        logger.info("SYSTEM READY - USAGE EXAMPLE")
        logger.info("="*60)

        example_code = '''
# Example usage:
import asyncio
from custom_search_engine_updated import CustomSearchEngine

async def search_prompts():
    # Initialize search engine
    search_engine = CustomSearchEngine(
        db_config={
            'host': 'localhost',
            'database': 'prompt_flow',
            'user': 'bao',
            'password': ''
        },
        vector_strategy='annoy'  # or 'multi_index', 'hybrid'
    )

    # Load pre-built indices (fast startup)
    search_engine.load_indices("search_indices/prompt_flow_indices")

    # Search your prompts
    results = await search_engine.search(
        "Help me create a comprehensive business plan",
        {
            'k': 10,
            'domains': ['business', 'strategy'],
            'task_types': ['generate', 'plan'],
            'expand_graph': True,
            'target_complexity': 4
        }
    )

    # Display results
    for i, result in enumerate(results, 1):
        print(f"{i}. {result.prompt_id}")
        print(f"   Score: {result.score:.3f}")
        print(f"   Sources: {', '.join(result.retrieval_sources)}")
        print(f"   {result.explanation}")
        print()

# Run the search
asyncio.run(search_prompts())
        '''

        logger.info(example_code)

        logger.info("Next steps:")
        logger.info("1. Run the example code above to test your system")
        logger.info("2. Modify search parameters based on your needs")
        logger.info("3. Integration with your workflow tools")

async def main():
    """Main setup function"""
    # Check if config paths exist
    if not CONFIG['prompts_path'].exists():
        logger.error(f"Prompts path does not exist: {CONFIG['prompts_path']}")
        logger.info("Please update the CONFIG paths at the top of this script")
        logger.info("Your prompts should be in: /home/bao/Documents/Obsidian/Main-Vault/Areas/AI/Prompts")
        return

    # Set API key if provided via environment
    if os.getenv('ANTHROPIC_API_KEY'):
        CONFIG['batch_classification']['anthropic_api_key'] = os.getenv('ANTHROPIC_API_KEY')

    # Run setup
    setup = CompleteSystemSetup(CONFIG)
    success = await setup.run_complete_setup()

    if success:
        logger.info("\n🎉 Setup completed successfully!")
        logger.info("Your prompt search system is ready to use.")
    else:
        logger.error("\n❌ Setup failed. Check the logs above for details.")

if __name__ == "__main__":
    asyncio.run(main())