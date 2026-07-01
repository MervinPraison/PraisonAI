"""
Capabilities CLI Handler

Provides CLI commands for all LiteLLM endpoint capabilities.
"""

import argparse
import sys
from typing import Optional, List


class CapabilitiesHandler:
    """Handler for capabilities CLI commands."""
    
    @staticmethod
    def handle_audio(args, unknown_args):
        """Handle audio subcommands (transcribe, speech)."""
        if not unknown_args:
            print("Usage: praisonai audio <transcribe|speech> [options]")
            print("\nSubcommands:")
            print("  transcribe  Transcribe audio to text")
            print("  speech      Convert text to speech")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "transcribe":
            return CapabilitiesHandler._handle_audio_transcribe(args, remaining_args)
        elif subcommand == "speech":
            return CapabilitiesHandler._handle_audio_speech(args, remaining_args)
        else:
            print(f"Unknown audio subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_audio_transcribe(args, remaining_args):
        """Handle: praisonai audio transcribe <file> [options]"""
        parser = argparse.ArgumentParser(prog="praisonai audio transcribe")
        parser.add_argument("file", help="Audio file to transcribe")
        parser.add_argument("--model", "-m", default="whisper-1", help="Model to use")
        parser.add_argument("--language", "-l", help="Language code (e.g., en, es)")
        parser.add_argument("--format", "-f", default="text", 
                           choices=["json", "text", "srt", "vtt", "verbose_json"],
                           help="Output format")
        parser.add_argument("--output", "-o", help="Output file path")
        parser.add_argument("--prompt", "-p", help="Prompt to guide transcription")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.audio import transcribe
        
        try:
            result = transcribe(
                audio=parsed.file,
                model=parsed.model,
                language=parsed.language,
                prompt=parsed.prompt,
                response_format=parsed.format,
            )
            
            if parsed.output:
                with open(parsed.output, 'w') as f:
                    f.write(result.text)
                print(f"Transcription saved to: {parsed.output}")
            else:
                print(result.text)
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_audio_speech(args, remaining_args):
        """Handle: praisonai audio speech <text> [options]"""
        parser = argparse.ArgumentParser(prog="praisonai audio speech")
        parser.add_argument("text", help="Text to convert to speech")
        parser.add_argument("--model", "-m", default="tts-1", help="Model to use")
        parser.add_argument("--voice", "-v", default="alloy", 
                           choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                           help="Voice to use")
        parser.add_argument("--format", "-f", default="mp3",
                           choices=["mp3", "opus", "aac", "flac", "wav", "pcm"],
                           help="Output format")
        parser.add_argument("--output", "-o", default="output.mp3", help="Output file path")
        parser.add_argument("--speed", "-s", type=float, default=1.0, help="Speed (0.25-4.0)")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.audio import speech
        
        try:
            result = speech(
                text=parsed.text,
                model=parsed.model,
                voice=parsed.voice,
                response_format=parsed.format,
                speed=parsed.speed,
            )
            
            result.save(parsed.output)
            print(f"Audio saved to: {parsed.output}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_images(args, unknown_args):
        """Handle images subcommands."""
        if not unknown_args:
            print("Usage: praisonai images <generate|edit> [options]")
            print("\nSubcommands:")
            print("  generate  Generate images from text")
            print("  edit      Edit an existing image")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "generate":
            return CapabilitiesHandler._handle_images_generate(args, remaining_args)
        elif subcommand == "edit":
            return CapabilitiesHandler._handle_images_edit(args, remaining_args)
        else:
            print(f"Unknown images subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_images_generate(args, remaining_args):
        """Handle: praisonai images generate <prompt> [options]"""
        parser = argparse.ArgumentParser(prog="praisonai images generate")
        parser.add_argument("prompt", help="Text description of the image")
        parser.add_argument("--model", "-m", default="dall-e-3", help="Model to use")
        parser.add_argument("--size", "-s", default="1024x1024", help="Image size")
        parser.add_argument("--quality", "-q", default="standard", choices=["standard", "hd"])
        parser.add_argument("--output", "-o", default="output.png", help="Output file path")
        parser.add_argument("--n", type=int, default=1, help="Number of images")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.images import image_generate
        
        try:
            results = image_generate(
                prompt=parsed.prompt,
                model=parsed.model,
                size=parsed.size,
                quality=parsed.quality,
                n=parsed.n,
            )
            
            for i, result in enumerate(results):
                output_path = parsed.output if len(results) == 1 else f"{parsed.output.rsplit('.', 1)[0]}_{i}.{parsed.output.rsplit('.', 1)[1]}"
                result.save(output_path)
                print(f"Image saved to: {output_path}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_images_edit(args, remaining_args):
        """Handle: praisonai images edit <image> <prompt> [options]"""
        parser = argparse.ArgumentParser(prog="praisonai images edit")
        parser.add_argument("image", help="Image file to edit")
        parser.add_argument("prompt", help="Edit description")
        parser.add_argument("--mask", help="Mask image file")
        parser.add_argument("--output", "-o", default="output.png", help="Output file path")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.images import image_edit
        
        try:
            results = image_edit(
                image=parsed.image,
                prompt=parsed.prompt,
                mask=parsed.mask,
            )
            
            for i, result in enumerate(results):
                output_path = parsed.output if len(results) == 1 else f"{parsed.output.rsplit('.', 1)[0]}_{i}.{parsed.output.rsplit('.', 1)[1]}"
                result.save(output_path)
                print(f"Image saved to: {output_path}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_files(args, unknown_args):
        """Handle files subcommands."""
        if not unknown_args:
            print("Usage: praisonai files <upload|list|get|delete> [options]")
            print("\nSubcommands:")
            print("  upload   Upload a file")
            print("  list     List uploaded files")
            print("  get      Get file info")
            print("  delete   Delete a file")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "upload":
            return CapabilitiesHandler._handle_files_upload(args, remaining_args)
        elif subcommand == "list":
            return CapabilitiesHandler._handle_files_list(args, remaining_args)
        elif subcommand == "get":
            return CapabilitiesHandler._handle_files_get(args, remaining_args)
        elif subcommand == "delete":
            return CapabilitiesHandler._handle_files_delete(args, remaining_args)
        else:
            print(f"Unknown files subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_files_upload(args, remaining_args):
        """Handle: praisonai files upload <file> [options]"""
        parser = argparse.ArgumentParser(prog="praisonai files upload")
        parser.add_argument("file", help="File to upload")
        parser.add_argument("--purpose", "-p", default="assistants",
                           choices=["assistants", "batch", "fine-tune"],
                           help="Purpose of the file")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.files import file_create
        
        try:
            result = file_create(
                file=parsed.file,
                purpose=parsed.purpose,
            )
            
            print(f"File uploaded: {result.id}")
            print(f"  Filename: {result.filename}")
            print(f"  Purpose: {result.purpose}")
            print(f"  Bytes: {result.bytes}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_files_list(args, remaining_args):
        """Handle: praisonai files list [options]"""
        parser = argparse.ArgumentParser(prog="praisonai files list")
        parser.add_argument("--purpose", "-p", help="Filter by purpose")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.files import file_list
        
        try:
            results = file_list(purpose=parsed.purpose)
            
            if not results:
                print("No files found.")
            else:
                for f in results:
                    print(f"{f.id}: {f.filename} ({f.purpose})")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_files_get(args, remaining_args):
        """Handle: praisonai files get <file_id>"""
        parser = argparse.ArgumentParser(prog="praisonai files get")
        parser.add_argument("file_id", help="File ID")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.files import file_retrieve
        
        try:
            result = file_retrieve(file_id=parsed.file_id)
            
            print(f"File: {result.id}")
            print(f"  Filename: {result.filename}")
            print(f"  Purpose: {result.purpose}")
            print(f"  Bytes: {result.bytes}")
            print(f"  Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_files_delete(args, remaining_args):
        """Handle: praisonai files delete <file_id>"""
        parser = argparse.ArgumentParser(prog="praisonai files delete")
        parser.add_argument("file_id", help="File ID")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.files import file_delete
        
        try:
            result = file_delete(file_id=parsed.file_id)
            
            if result:
                print(f"File deleted: {parsed.file_id}")
            else:
                print(f"Failed to delete file: {parsed.file_id}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_embed(args, unknown_args):
        """Handle embed command."""
        parser = argparse.ArgumentParser(prog="praisonai embed")
        parser.add_argument("text", nargs="+", help="Text to embed")
        parser.add_argument("--model", "-m", default="text-embedding-3-small", help="Model to use")
        parser.add_argument("--dimensions", "-d", type=int, help="Output dimensions")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonaiagents.embedding import embedding
        
        try:
            text_input = " ".join(parsed.text)
            result = embedding(
                input=text_input,
                model=parsed.model,
                dimensions=parsed.dimensions,
            )
            
            print(f"Embeddings generated: {len(result.embeddings)} vectors")
            print(f"Dimensions: {len(result.embeddings[0]) if result.embeddings else 0}")
            if result.usage:
                print(f"Tokens: {result.usage.get('total_tokens', 0)}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_rerank(args, unknown_args):
        """Handle rerank command."""
        parser = argparse.ArgumentParser(prog="praisonai rerank")
        parser.add_argument("query", help="Query to rank against")
        parser.add_argument("--documents", "-d", nargs="+", required=True, help="Documents to rank")
        parser.add_argument("--model", "-m", default="cohere/rerank-english-v3.0", help="Model to use")
        parser.add_argument("--top-n", "-n", type=int, help="Number of top results")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.rerank import rerank
        
        try:
            result = rerank(
                query=parsed.query,
                documents=parsed.documents,
                model=parsed.model,
                top_n=parsed.top_n,
            )
            
            print(f"Ranked {len(result.results)} documents:")
            for r in result.results:
                print(f"  [{r['index']}] Score: {r['relevance_score']:.4f}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_moderate(args, unknown_args):
        """Handle moderate command."""
        parser = argparse.ArgumentParser(prog="praisonai moderate")
        parser.add_argument("text", nargs="+", help="Text to moderate")
        parser.add_argument("--model", "-m", default="omni-moderation-latest", help="Model to use")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.moderations import moderate
        
        try:
            text_input = " ".join(parsed.text)
            results = moderate(
                input=text_input,
                model=parsed.model,
            )
            
            for i, result in enumerate(results):
                print(f"Result {i + 1}:")
                print(f"  Flagged: {result.flagged}")
                if result.flagged:
                    flagged_categories = [k for k, v in result.categories.items() if v]
                    print(f"  Categories: {', '.join(flagged_categories)}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_ocr(args, unknown_args):
        """Handle ocr command."""
        parser = argparse.ArgumentParser(prog="praisonai ocr")
        parser.add_argument("document", help="Document or image to process")
        parser.add_argument("--model", "-m", default="mistral/mistral-ocr-latest", help="Model to use")
        parser.add_argument("--output", "-o", help="Output file path")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.ocr import ocr
        
        try:
            result = ocr(
                document=parsed.document,
                model=parsed.model,
            )
            
            if parsed.output:
                with open(parsed.output, 'w') as f:
                    f.write(result.text)
                print(f"OCR result saved to: {parsed.output}")
            else:
                print(result.text)
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_batches(args, unknown_args):
        """Handle batches subcommands."""
        if not unknown_args:
            print("Usage: praisonai batches <create|list|get|cancel> [options]")
            print("\nSubcommands:")
            print("  create   Create a batch job")
            print("  list     List batch jobs")
            print("  get      Get batch status")
            print("  cancel   Cancel a batch job")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_batches_create(args, remaining_args)
        elif subcommand == "list":
            return CapabilitiesHandler._handle_batches_list(args, remaining_args)
        elif subcommand == "get":
            return CapabilitiesHandler._handle_batches_get(args, remaining_args)
        elif subcommand == "cancel":
            return CapabilitiesHandler._handle_batches_cancel(args, remaining_args)
        else:
            print(f"Unknown batches subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_batches_create(args, remaining_args):
        """Handle: praisonai batches create <file_id>"""
        parser = argparse.ArgumentParser(prog="praisonai batches create")
        parser.add_argument("file_id", help="Input file ID")
        parser.add_argument("--endpoint", "-e", default="/v1/chat/completions",
                           choices=["/v1/chat/completions", "/v1/embeddings"])
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.batches import batch_create
        
        try:
            result = batch_create(
                input_file_id=parsed.file_id,
                endpoint=parsed.endpoint,
            )
            
            print(f"Batch created: {result.id}")
            print(f"  Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_batches_list(args, remaining_args):
        """Handle: praisonai batches list"""
        from praisonai.capabilities.batches import batch_list
        
        try:
            results = batch_list()
            
            if not results:
                print("No batches found.")
            else:
                for b in results:
                    print(f"{b.id}: {b.status} ({b.endpoint})")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_batches_get(args, remaining_args):
        """Handle: praisonai batches get <batch_id>"""
        parser = argparse.ArgumentParser(prog="praisonai batches get")
        parser.add_argument("batch_id", help="Batch ID")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.batches import batch_retrieve
        
        try:
            result = batch_retrieve(batch_id=parsed.batch_id)
            
            print(f"Batch: {result.id}")
            print(f"  Status: {result.status}")
            print(f"  Endpoint: {result.endpoint}")
            if result.request_counts:
                print(f"  Completed: {result.request_counts.get('completed', 0)}/{result.request_counts.get('total', 0)}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_batches_cancel(args, remaining_args):
        """Handle: praisonai batches cancel <batch_id>"""
        parser = argparse.ArgumentParser(prog="praisonai batches cancel")
        parser.add_argument("batch_id", help="Batch ID")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.batches import batch_cancel
        
        try:
            result = batch_cancel(batch_id=parsed.batch_id)
            
            print(f"Batch cancelled: {result.id}")
            print(f"  Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_vector_stores(args, unknown_args):
        """Handle vector-stores subcommands."""
        if not unknown_args:
            print("Usage: praisonai vector-stores <create|search> [options]")
            print("\nSubcommands:")
            print("  create   Create a vector store")
            print("  search   Search a vector store")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_vector_stores_create(args, remaining_args)
        elif subcommand == "search":
            return CapabilitiesHandler._handle_vector_stores_search(args, remaining_args)
        else:
            print(f"Unknown vector-stores subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_vector_stores_create(args, remaining_args):
        """Handle: praisonai vector-stores create <name>"""
        parser = argparse.ArgumentParser(prog="praisonai vector-stores create")
        parser.add_argument("name", help="Vector store name")
        parser.add_argument("--file-ids", "-f", nargs="+", help="File IDs to add")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.vector_stores import vector_store_create
        
        try:
            result = vector_store_create(
                name=parsed.name,
                file_ids=parsed.file_ids,
            )
            
            print(f"Vector store created: {result.id}")
            print(f"  Name: {result.name}")
            print(f"  Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_vector_stores_search(args, remaining_args):
        """Handle: praisonai vector-stores search <store_id> <query>"""
        parser = argparse.ArgumentParser(prog="praisonai vector-stores search")
        parser.add_argument("store_id", help="Vector store ID")
        parser.add_argument("query", help="Search query")
        parser.add_argument("--max-results", "-n", type=int, default=10, help="Max results")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.vector_stores import vector_store_search
        
        try:
            result = vector_store_search(
                vector_store_id=parsed.store_id,
                query=parsed.query,
                max_num_results=parsed.max_results,
            )
            
            print(f"Search results for: {result.query}")
            for i, r in enumerate(result.results):
                print(f"  [{i + 1}] Score: {r.get('score', 0):.4f}")
                if 'content' in r:
                    for c in r['content'][:1]:  # Show first content
                        text = c.get('text', '')[:100]
                        print(f"      {text}...")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_assistants(args, unknown_args):
        """Handle assistants subcommands."""
        if not unknown_args:
            print("Usage: praisonai assistants <create|list> [options]")
            print("\nSubcommands:")
            print("  create   Create an assistant")
            print("  list     List assistants")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_assistants_create(args, remaining_args)
        elif subcommand == "list":
            return CapabilitiesHandler._handle_assistants_list(args, remaining_args)
        else:
            print(f"Unknown assistants subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_assistants_create(args, remaining_args):
        """Handle: praisonai assistants create [options]"""
        parser = argparse.ArgumentParser(prog="praisonai assistants create")
        parser.add_argument("--name", "-n", required=True, help="Assistant name")
        parser.add_argument("--instructions", "-i", help="System instructions")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model to use")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.assistants import assistant_create
        
        try:
            result = assistant_create(
                name=parsed.name,
                instructions=parsed.instructions,
                model=parsed.model,
            )
            
            print(f"Assistant created: {result.id}")
            print(f"  Name: {result.name}")
            print(f"  Model: {result.model}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_assistants_list(args, remaining_args):
        """Handle: praisonai assistants list"""
        from praisonai.capabilities.assistants import assistant_list
        
        try:
            results = assistant_list()
            
            if not results:
                print("No assistants found.")
            else:
                for a in results:
                    print(f"{a.id}: {a.name} ({a.model})")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_fine_tuning(args, unknown_args):
        """Handle fine-tuning subcommands."""
        if not unknown_args:
            print("Usage: praisonai fine-tuning <create|list> [options]")
            print("\nSubcommands:")
            print("  create   Create a fine-tuning job")
            print("  list     List fine-tuning jobs")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_fine_tuning_create(args, remaining_args)
        elif subcommand == "list":
            return CapabilitiesHandler._handle_fine_tuning_list(args, remaining_args)
        else:
            print(f"Unknown fine-tuning subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_fine_tuning_create(args, remaining_args):
        """Handle: praisonai fine-tuning create <file_id>"""
        parser = argparse.ArgumentParser(prog="praisonai fine-tuning create")
        parser.add_argument("file_id", help="Training file ID")
        parser.add_argument("--model", "-m", default="gpt-4o-mini-2024-07-18", help="Base model")
        parser.add_argument("--suffix", "-s", help="Model name suffix")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.fine_tuning import fine_tuning_create
        
        try:
            result = fine_tuning_create(
                training_file=parsed.file_id,
                model=parsed.model,
                suffix=parsed.suffix,
            )
            
            print(f"Fine-tuning job created: {result.id}")
            print(f"  Status: {result.status}")
            print(f"  Model: {result.model}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_fine_tuning_list(args, remaining_args):
        """Handle: praisonai fine-tuning list"""
        from praisonai.capabilities.fine_tuning import fine_tuning_list
        
        try:
            results = fine_tuning_list()
            
            if not results:
                print("No fine-tuning jobs found.")
            else:
                for j in results:
                    print(f"{j.id}: {j.status} ({j.model})")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_completions(args, unknown_args):
        """Handle completions subcommands."""
        parser = argparse.ArgumentParser(prog="praisonai completions")
        parser.add_argument("prompt", nargs="?", help="Prompt text")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model to use")
        parser.add_argument("--max-tokens", type=int, help="Maximum tokens")
        parser.add_argument("--temperature", "-t", type=float, default=1.0, help="Temperature")
        parser.add_argument("--system", "-s", help="System prompt")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        if not parsed.prompt:
            print("Usage: praisonai completions <prompt> [options]")
            return 1
        
        from praisonai.capabilities.completions import chat_completion
        
        try:
            messages = []
            if parsed.system:
                messages.append({"role": "system", "content": parsed.system})
            messages.append({"role": "user", "content": parsed.prompt})
            
            result = chat_completion(
                messages=messages,
                model=parsed.model,
                temperature=parsed.temperature,
                max_tokens=parsed.max_tokens,
            )
            
            print(result.content)
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_messages(args, unknown_args):
        """Handle messages subcommands."""
        if not unknown_args:
            print("Usage: praisonai messages <create|count-tokens> [options]")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_messages_create(args, remaining_args)
        elif subcommand == "count-tokens":
            return CapabilitiesHandler._handle_count_tokens(args, remaining_args)
        else:
            print(f"Unknown messages subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_messages_create(args, remaining_args):
        """Handle: praisonai messages create <prompt>"""
        parser = argparse.ArgumentParser(prog="praisonai messages create")
        parser.add_argument("prompt", help="Prompt text")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model")
        parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens")
        parser.add_argument("--system", "-s", help="System prompt")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.messages import messages_create
        
        try:
            result = messages_create(
                messages=[{"role": "user", "content": parsed.prompt}],
                model=parsed.model,
                max_tokens=parsed.max_tokens,
                system=parsed.system,
            )
            
            if result.content:
                for block in result.content:
                    if block.get("type") == "text":
                        print(block.get("text", ""))
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_count_tokens(args, remaining_args):
        """Handle: praisonai messages count-tokens <text>"""
        parser = argparse.ArgumentParser(prog="praisonai messages count-tokens")
        parser.add_argument("text", help="Text to count tokens for")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model for tokenization")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.messages import count_tokens
        
        try:
            result = count_tokens(
                messages=[{"role": "user", "content": parsed.text}],
                model=parsed.model,
            )
            
            print(f"Token count: {result.input_tokens}")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_guardrails(args, unknown_args):
        """Handle guardrails subcommands."""
        parser = argparse.ArgumentParser(prog="praisonai guardrails")
        parser.add_argument("content", help="Content to check")
        parser.add_argument("--rules", "-r", nargs="+", help="Rules to apply")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model to use")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.guardrails import apply_guardrail
        
        try:
            result = apply_guardrail(
                content=parsed.content,
                rules=parsed.rules,
                model=parsed.model,
            )
            
            if result.passed:
                print("Content passed guardrail check")
            else:
                print("Content failed guardrail check")
                if result.violations:
                    for v in result.violations:
                        print(f"  - {v}")
            
            return 0 if result.passed else 1
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_rag(args, unknown_args):
        """Handle RAG subcommands."""
        parser = argparse.ArgumentParser(prog="praisonai rag")
        parser.add_argument("query", help="Query string")
        parser.add_argument("--documents", "-d", nargs="+", help="Documents to search")
        parser.add_argument("--vector-store", "-v", help="Vector store ID")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model to use")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.rag import rag_query
        
        try:
            result = rag_query(
                query=parsed.query,
                documents=parsed.documents,
                vector_store_id=parsed.vector_store,
                model=parsed.model,
            )
            
            print(result.answer)
            
            if result.sources:
                print("\nSources:")
                for s in result.sources[:3]:
                    print(f"  - {s.get('text', '')[:100]}...")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_realtime(args, unknown_args):
        """Handle realtime subcommands."""
        parser = argparse.ArgumentParser(prog="praisonai realtime")
        parser.add_argument("action", choices=["connect", "info"], help="Action")
        parser.add_argument("--model", "-m", default="gpt-4o-realtime-preview", help="Model")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.realtime import realtime_connect
        
        try:
            if parsed.action == "connect":
                session = realtime_connect(model=parsed.model)
                print(f"Session ID: {session.id}")
                print(f"URL: {session.url}")
                print(f"Status: {session.status}")
            else:
                print("Realtime API info:")
                print("  - Supports audio/text modalities")
                print("  - Use WebSocket connection for streaming")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_videos(args, unknown_args):
        """Handle video generation."""
        parser = argparse.ArgumentParser(prog="praisonai videos")
        parser.add_argument("prompt", help="Video description")
        parser.add_argument("--model", "-m", default="sora", help="Model to use")
        parser.add_argument("--output", "-o", help="Output file path")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.videos import video_generate
        
        try:
            result = video_generate(
                prompt=parsed.prompt,
                model=parsed.model,
            )
            
            print(f"Video ID: {result.id}")
            if result.url:
                print(f"URL: {result.url}")
            print(f"Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_a2a(args, unknown_args):
        """Handle agent-to-agent communication."""
        parser = argparse.ArgumentParser(prog="praisonai a2a")
        parser.add_argument("message", help="Message to send")
        parser.add_argument("--target", "-t", required=True, help="Target agent name")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.a2a import a2a_send
        
        try:
            result = a2a_send(
                message=parsed.message,
                target_agent=parsed.target,
            )
            
            print(f"Message ID: {result.id}")
            print(f"Status: {result.status}")
            if result.response:
                print(f"Response: {result.response}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_containers(args, unknown_args):
        """Handle container operations."""
        if not unknown_args:
            print("Usage: praisonai containers <create|files> [options]")
            return 1
        
        subcommand = unknown_args[0]
        remaining_args = unknown_args[1:]
        
        if subcommand == "create":
            return CapabilitiesHandler._handle_container_create(args, remaining_args)
        elif subcommand == "files":
            return CapabilitiesHandler._handle_container_files(args, remaining_args)
        else:
            print(f"Unknown containers subcommand: {subcommand}")
            return 1
    
    @staticmethod
    def _handle_container_create(args, remaining_args):
        """Handle: praisonai containers create"""
        parser = argparse.ArgumentParser(prog="praisonai containers create")
        parser.add_argument("--image", "-i", default="python:3.11", help="Container image")
        parser.add_argument("--name", "-n", help="Container name")
        
        try:
            parsed = parser.parse_args(remaining_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.containers import container_create
        
        try:
            result = container_create(
                image=parsed.image,
                name=parsed.name,
            )
            
            print(f"Container ID: {result.id}")
            print(f"Status: {result.status}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def _handle_container_files(args, remaining_args):
        """Handle: praisonai containers files <action>"""
        if not remaining_args:
            print("Usage: praisonai containers files <read|write|list> [options]")
            return 1
        
        action = remaining_args[0]
        action_args = remaining_args[1:]
        
        if action == "read":
            parser = argparse.ArgumentParser(prog="praisonai containers files read")
            parser.add_argument("container_id", help="Container ID")
            parser.add_argument("path", help="File path")
            
            try:
                parsed = parser.parse_args(action_args)
            except SystemExit:
                return 1
            
            from praisonai.capabilities.container_files import container_file_read
            
            try:
                result = container_file_read(
                    container_id=parsed.container_id,
                    path=parsed.path,
                )
                
                if result.content:
                    print(result.content)
                else:
                    print("(empty or not available)")
                
                return 0
            except Exception as e:
                print(f"Error: {e}")
                return 1
        
        elif action == "list":
            parser = argparse.ArgumentParser(prog="praisonai containers files list")
            parser.add_argument("container_id", help="Container ID")
            parser.add_argument("--path", "-p", default="/", help="Directory path")
            
            try:
                parsed = parser.parse_args(action_args)
            except SystemExit:
                return 1
            
            from praisonai.capabilities.container_files import container_file_list
            
            try:
                results = container_file_list(
                    container_id=parsed.container_id,
                    path=parsed.path,
                )
                
                if not results:
                    print("No files found.")
                else:
                    for f in results:
                        print(f.path)
                
                return 0
            except Exception as e:
                print(f"Error: {e}")
                return 1
        
        else:
            print(f"Unknown action: {action}")
            return 1
    
    @staticmethod
    def handle_passthrough(args, unknown_args):
        """Handle passthrough API calls."""
        parser = argparse.ArgumentParser(prog="praisonai passthrough")
        parser.add_argument("provider", help="Provider name")
        parser.add_argument("endpoint", help="API endpoint")
        parser.add_argument("--method", "-X", default="POST", help="HTTP method")
        parser.add_argument("--data", "-d", help="JSON data")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.passthrough import passthrough
        import json
        
        try:
            data = json.loads(parsed.data) if parsed.data else None
            
            result = passthrough(
                provider=parsed.provider,
                endpoint=parsed.endpoint,
                method=parsed.method,
                data=data,
            )
            
            print(f"Status: {result.status_code}")
            if result.data:
                print(json.dumps(result.data, indent=2))
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_responses(args, unknown_args):
        """Handle responses API."""
        parser = argparse.ArgumentParser(prog="praisonai responses")
        parser.add_argument("input", help="Input text")
        parser.add_argument("--model", "-m", default="gpt-4o-mini", help="Model")
        parser.add_argument("--instructions", "-i", help="Instructions")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.responses import responses_create
        
        try:
            result = responses_create(
                input=parsed.input,
                model=parsed.model,
                instructions=parsed.instructions,
            )
            
            print(result.output or "(no output)")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    @staticmethod
    def handle_search(args, unknown_args):
        """Handle search operations."""
        parser = argparse.ArgumentParser(prog="praisonai search")
        parser.add_argument("query", help="Search query")
        parser.add_argument("--max-results", "-n", type=int, default=5, help="Max results")
        
        try:
            parsed = parser.parse_args(unknown_args)
        except SystemExit:
            return 1
        
        from praisonai.capabilities.search import search
        
        try:
            result = search(
                query=parsed.query,
                max_results=parsed.max_results,
            )
            
            if not result.results:
                print("No results found.")
            else:
                for r in result.results:
                    title = r.get("title", "Untitled")
                    url = r.get("url", "")
                    print(f"- {title}")
                    if url:
                        print(f"  {url}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
