from docx import Document

path = r'C:\Users\Sanskar\OneDrive\Desktop\Internship\Trade_Stock_Project-main\Trade_Stock_Project-main\Testing_Report_Simple.docx'

doc = Document(path)

old = [
    'This report documents the testing of the stock trading guidance website. The platform fetches live NIFTY 50 market data, runs machine learning models to predict short-term price movement, and applies risk-management rules to guide a trade. The screenshots below were captured while testing the live website and confirm that each part of the system is working correctly.',
    'This screenshot shows the Co-Pilot panel tracking an open ADANIPORTS trade in real time. It displays the current market price, the protected (stop-loss) price, the target price, and the live profit/loss, all updating automatically. Below it, the Market Guardian panel gives a plain-language caution message, telling the user the trend is still bullish but that the entry quality is weak. This confirms that the live monitoring and alert system is working as intended.',
    'This screenshot shows the detailed calculations behind the same trade: the dynamic stop-loss and target prices, the ATR (volatility) value, and the risk/reward ratio. It also shows the order analysis (capital required, potential profit, and maximum risk), the position-sizing recommendation, and the machine learning model\'s output — trade score, confidence, predicted return, and overall market trend. This confirms that the risk-management engine and the ML prediction model are both calculating and displaying results correctly.',
    'Here the stock share prices match real with NSE so the Data is fetching correctly.',
    'This screenshot shows the live prediction card for Britannia, including its sector, current price, price change, and a \'Syncing\' status indicating a live data connection. It also shows the model\'s predicted return, trade score, confidence level, and risk rating for this stock. This confirms that the prediction card updates correctly for each stock and clearly presents the model\'s output to the user.',
    'Based on this testing, all the core features of the website — live market data, Co-Pilot trade monitoring, risk-management calculations, and ML-based predictions — are working correctly. The website is functioning as intended and is ready to be demonstrated.'
]

new = [
    'This testing report evaluates the functionality, data accuracy, and decision-support performance of the NIFTY 50 ML trading guidance platform. The system is designed to fetch live market information, apply machine learning-based trade analysis, and present risk-managed guidance for short-term trading decisions. During validation, the screenshots confirm that the core platform components are operating as intended and that the user interface is presenting meaningful market and prediction data.',
    'The Co-Pilot trade panel demonstrates live monitoring of an ADANIPORTS position. It displays the current market price, protected stop-loss level, target value, and live profit/loss, with values updating in real time. The Market Guardian section also provides a clear interpretation of trend direction and entry quality, confirming that the monitoring and alerting layer is functional and effectively communicates trade conditions to the user.',
    'This section validates the risk-management and model-analysis logic of the platform. It presents the dynamic stop-loss and target levels, ATR-based volatility measure, risk-to-reward ratio, capital requirement, expected profit, maximum risk, position-sizing suggestion, and ML-derived outputs such as trade score, confidence level, predicted return, and overall market trend. The results confirm that the system is calculating and displaying risk controls and prediction metrics correctly for trading decision support.',
    'The live stock price values were observed to match the real-time NSE data, confirming that market data is being retrieved correctly. This is a critical validation point because accurate live data ensures that the prediction engine and risk calculations are based on reliable inputs.',
    'This prediction card confirms the real-time analysis of Britannia stock. It includes sector information, current price, price movement, live syncing status, expected return, trade score, confidence level, and risk rating. The consistent update of these values indicates that the prediction card is functioning correctly and is effectively presenting model-generated output to the user.',
    'Based on the testing observations, the website successfully demonstrates the principal features expected of a trading decision-support system: live market data integration, real-time position monitoring, risk-management evaluation, and ML-based prediction analysis. The platform is functioning effectively for its intended purpose and provides a practical and useful decision-support experience for NIFTY 50 trading analysis.'
]

for p in doc.paragraphs:
    text = p.text.strip()
    for idx, old_text in enumerate(old):
        if text == old_text:
            p.text = new[idx]
            break

doc.save(path)
print('Updated document saved:', path)
