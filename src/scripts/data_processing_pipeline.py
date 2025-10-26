#!/usr/bin/env python3
"""
Pipeline de processamento de dados de livros.

Executa limpeza de dados e feature engineering em sequência.

Uso:
    python data_processing_pipeline.py
"""

import logging
import time
from pathlib import Path
from src.scripts.data_cleaning import run_cleaning_pipeline
from src.scripts.data_types import PipelineConfig
from src.scripts.feature_engineering import run_feature_pipeline

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_pipeline(config: PipelineConfig = None) -> dict:
    """
    Executa a pipeline completa: limpeza + feature engineering.
    
    Args:
        config: Configuração da pipeline (usa padrão se None)
        
    Returns:
        dict: Estatísticas da execução
    """
    start_time = time.time()
    
    if config is None:
        config = PipelineConfig()
    
    logger.info("[>>] Iniciando pipeline de processamento de dados")
    
    try:
        # Verificar arquivo de entrada
        input_file = Path(config.input_file)
        if not input_file.exists():
            raise FileNotFoundError(f"Arquivo de entrada não encontrado: {config.input_file}")
        
        # Criar diretórios de saída
        Path(config.processed_output).parent.mkdir(parents=True, exist_ok=True)
        Path(config.features_output).parent.mkdir(parents=True, exist_ok=True)
        
        # FASE 1: Limpeza
        logger.info("[1/2] FASE 1: Limpeza de dados")
        processed_df, cleaning_stats = run_cleaning_pipeline(
            config.input_file,
            config.processed_output,
            config
        )
        logger.info(f"[OK] Limpeza concluida: {cleaning_stats['processed_records']} registros")
        
        # FASE 2: Feature Engineering
        logger.info("[2/2] FASE 2: Feature engineering")
        features_df, features_stats = run_feature_pipeline(
            config.processed_output,
            config.features_output,
            config
        )
        logger.info(f"[OK] Features criadas: {features_stats['features_created']}")
        
        # Resumo final
        execution_time = time.time() - start_time
        logger.info("=" * 60)
        logger.info("[INFO] RESUMO DA PIPELINE")
        logger.info(f"  Total de registros: {cleaning_stats['total_records']}")
        logger.info(f"  Features criadas: {features_stats['features_created']}")
        logger.info(f"  Tempo de execucao: {execution_time:.2f}s")
        logger.info(f"  Dados processados: {config.processed_output}")
        logger.info(f"  Dados com features: {config.features_output}")
        logger.info("=" * 60)
        logger.info("[OK] Pipeline concluida com sucesso!")
        
        return {
            "total_records": cleaning_stats["total_records"],
            "processed_records": cleaning_stats["processed_records"],
            "features_created": features_stats["features_created"],
            "execution_time_seconds": execution_time,
        }
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"[ERROR] Erro na pipeline apos {execution_time:.2f}s: {str(e)}")
        raise


if __name__ == "__main__":
    try:
        stats = run_pipeline()
        print(f"\n[OK] Pipeline executada com sucesso em {stats['execution_time_seconds']:.2f}s")
    except Exception as e:
        print(f"\n[ERROR] Erro na execucao: {str(e)}")
        exit(1)
