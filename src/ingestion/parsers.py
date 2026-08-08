import os
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger()

class BaseParser:
    def parse_pdf(self, pdf_path: str) -> Optional[str]:
        raise NotImplementedError("Subclasses must implement parse_pdf")

class MarkItDownParser(BaseParser):
    def parse_pdf(self, pdf_path: str) -> Optional[str]:
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(pdf_path)
            logger.info(f"MarkItDown parser successfully processed {pdf_path}")
            return result.text_content
        except Exception as e:
            logger.error(f"MarkItDown parser failed: {e}")
            return None

class DoclingParser(BaseParser):
    def __init__(self, use_cpu: bool = None):
        if use_cpu is None:
            try:
                import torch
                self.use_cpu = not torch.cuda.is_available()
            except ImportError:
                self.use_cpu = True
        else:
            self.use_cpu = use_cpu

    def parse_pdf(self, pdf_path: str) -> Optional[str]:
        try:
            if self.use_cpu:
                os.environ["CUDA_VISIBLE_DEVICES"] = ""

            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions

            logger.info("Initializing Docling with Formula extraction enabled...")

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            pipeline_options.do_formula_enrichment = True
            pipeline_options.images_scale = 1.0

            if self.use_cpu:
                pipeline_options.accelerator_options = AcceleratorOptions(
                    num_threads=4,
                    device="cpu"
                )
            else:
                pipeline_options.accelerator_options = AcceleratorOptions(
                    device="cuda"
                )

            converter = DocumentConverter(
                format_options={
                    "pdf": PdfFormatOption(pipeline_options=pipeline_options)
                }
            )

            logger.info(f"Processing {pdf_path}...")
            result = converter.convert(pdf_path)

            return result.document.export_to_markdown()
        except Exception as e:
            logger.error(f"Docling parser failed: {e}")
            return None

import subprocess
import shutil
import tempfile
from pathlib import Path

class MinerUParser(BaseParser):
    def __init__(self, use_cpu: bool = None):
        # Auto-detect GPU using torch if use_cpu is not explicitly set
        if use_cpu is None:
            try:
                import torch
                self.use_cpu = not torch.cuda.is_available()
            except ImportError:
                # Fallback to CPU if torch is not installed
                self.use_cpu = True
        else:
            self.use_cpu = use_cpu

    def parse_pdf(self, pdf_path: str) -> Optional[str]:
        if not shutil.which("mineru"):
            logger.error("MinerU ('mineru' command) is not installed or not in PATH.")
            return None

        abs_pdf_path = os.path.abspath(pdf_path)
        mineru_temp_output_dir = None

        try:
            mineru_temp_output_dir = tempfile.mkdtemp(prefix="mineru_output_")
            logger.info(f"Running MinerU via CLI on {abs_pdf_path}...")

            device_flag = "cpu" if self.use_cpu else "cuda"
            
            cmd = [
                "mineru",
                "-p", abs_pdf_path,
                "-o", mineru_temp_output_dir,
                "-m", "ocr",
                "--backend", "pipeline",
                "--device", device_flag
            ]

            env = os.environ.copy()
            if self.use_cpu:
                env["CUDA_VISIBLE_DEVICES"] = ""
            
            # Fix para WinError 1314 no Windows: desativa symlinks do HuggingFace
            env["HF_HUB_DISABLE_SYMLINKS"] = "1"

            result = subprocess.run(
                cmd,
                check=False,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            # Log command for debugging
            logger.info(f"MinerU command: {' '.join(cmd)}")

            if result.returncode != 0:
                logger.error(f"MinerU CLI Failed (Exit Code {result.returncode})")
                logger.error(f"MinerU STDOUT: {result.stdout}")
                logger.error(f"MinerU STDERR: {result.stderr}")
                return None

            # Busca exaustiva pelo arquivo .md
            found_md = None
            all_files = []
            for root, dirs, files in os.walk(mineru_temp_output_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    all_files.append(full_path)
                    if file.lower().endswith(".md"):
                        # Preferir arquivos que não sejam 'content_list.md' se houver outros
                        if not found_md or "content_list" not in file.lower():
                            found_md = full_path

            if found_md:
                logger.info(f"MinerU processing complete. File found: {found_md}")
                with open(found_md, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                return markdown_content
            else:
                logger.error(f"MinerU finished with code 0 but no Markdown file was found in: {mineru_temp_output_dir}")
                logger.error(f"Files found in output directory: {all_files}")
                logger.error(f"MinerU STDOUT: {result.stdout}")
                logger.error(f"MinerU STDERR: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"MinerU Execution Error: {e}")
            return None
        finally:
            if mineru_temp_output_dir and os.path.exists(mineru_temp_output_dir):
                shutil.rmtree(mineru_temp_output_dir)

def convert_pdf_to_markdown(pdf_path: str, parser_type: str = "mineru", output_dir: str = "output_md") -> Optional[str]:
    """
    Converte PDF para Markdown usando o parser especificado.
    Salva o resultado em um diretório e reutiliza se já existir.
    """
    pdf_path_obj = Path(pdf_path)
    if not pdf_path_obj.exists():
        logger.error(f"Arquivo PDF não encontrado: {pdf_path}")
        return None

    # Cria o diretório de saída se não existir
    os.makedirs(output_dir, exist_ok=True)
    
    # Define o nome do arquivo Markdown (cache)
    md_filename = f"{pdf_path_obj.stem}_{parser_type}.md"
    md_path = Path(output_dir) / md_filename

    # Verifica se o cache existe
    if md_path.exists():
        logger.info(f"Usando Markdown já gerado (cache): {md_path}")
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Erro ao ler arquivo de cache {md_path}: {e}")
            # Se falhar a leitura, continua para re-gerar

    parsers = {
        "markitdown": MarkItDownParser(),
        "docling": DoclingParser(),
        "mineru": MinerUParser()
    }
    
    if parser_type not in parsers:
        logger.error(f"Parser '{parser_type}' não suportado.")
        return None
        
    parser = parsers[parser_type]
    markdown_content = parser.parse_pdf(pdf_path)

    if markdown_content:
        # Salva o resultado no cache
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            logger.info(f"Markdown salvo com sucesso em: {md_path}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar o Markdown no cache: {e}")
            
    return markdown_content
