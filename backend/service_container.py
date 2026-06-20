from backend.market_feed import AlphaVantageProvider, OandaProvider, SampleDataProvider, UnifiedMarketFeed, YahooProvider
from backend.forex_factory_feed import ForexFactoryFeed
from charts.tradingview_renderer import TradingViewRenderer
from engine.analysis_orchestrator import AnalysisOrchestrator
from engine.indicator_engine import IndicatorEngine
from engine.news_intelligence_engine import NewsIntelligenceEngine
from engine.risk_engine import RiskEngine
from engine.signal_engine_v2 import SignalEngineV2
from engine.structure_engine import StructureEngine
from engine.support_resistance_engine import SupportResistanceEngine
from storage.cache import InMemoryTTLCache
from storage.news_signal_repository import NewsSignalRepository
from storage.signal_repository_v2 import JsonlSignalRepository


def build_container():
    cache = InMemoryTTLCache(ttl_seconds=30)
    market_feed = UnifiedMarketFeed(
        providers=[
            OandaProvider(),
            YahooProvider(),
            AlphaVantageProvider(),
            SampleDataProvider(),
        ],
        cache=cache,
    )
    indicator_engine = IndicatorEngine()
    structure_engine = StructureEngine()
    zone_engine = SupportResistanceEngine()
    risk_engine = RiskEngine()
    signal_engine = SignalEngineV2(risk_engine=risk_engine)
    renderer = TradingViewRenderer()
    signal_repository = JsonlSignalRepository()
    forex_factory_feed = ForexFactoryFeed()
    news_engine = NewsIntelligenceEngine()
    news_signal_repository = NewsSignalRepository()
    orchestrator = AnalysisOrchestrator(
        market_feed=market_feed,
        indicator_engine=indicator_engine,
        structure_engine=structure_engine,
        zone_engine=zone_engine,
        signal_engine=signal_engine,
        renderer=renderer,
        signal_repository=signal_repository,
        forex_factory_feed=forex_factory_feed,
        news_engine=news_engine,
        news_signal_repository=news_signal_repository,
    )
    return {
        "market_feed": market_feed,
        "analysis_orchestrator": orchestrator,
        "signal_repository": signal_repository,
        "forex_factory_feed": forex_factory_feed,
        "news_engine": news_engine,
        "news_signal_repository": news_signal_repository,
    }

