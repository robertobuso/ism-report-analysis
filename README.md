Of course\! Here is your `README` file formatted with Markdown for GitHub.

# ISM Report Analysis Platform

> An AI-powered web application for automated analysis of ISM (Institute for Supply Management) Manufacturing and Services reports. The platform uses advanced AI agents to extract, structure, validate, and visualize PMI (Purchasing Managers' Index) data from PDF reports.

-----

## 🚀 Features

  - 🤖 **AI-Powered Data Extraction**
      - Multi-Agent AI System using CrewAI framework
      - GPT-4o Integration for intelligent PDF parsing
      - Automatic Report Type Detection (Manufacturing vs. Services)
      - Data Validation & Correction with specialized AI agents
  - 📊 **Comprehensive Visualizations**
      - Interactive PMI Heatmaps with color-coded performance indicators
      - Time-Series Analysis with trend visualization
      - Industry Growth Tracking (alphabetical and numerical rankings)
      - Multi-Report Comparison Tools
      - Real-time Dashboard with KPI cards
  - 🗄️ **Data Management**
      - SQLite Database with automated schema management
      - Historical Data Analysis across multiple reporting periods
      - Google Sheets Integration for data export and collaboration
      - Persistent Storage with Railway volume mounting
  - 🔐 **Enterprise Features**
      - Google OAuth Authentication for secure access
      - Multi-User Support with session management
      - Responsive Design optimized for desktop and mobile
      - Production-Ready Deployment with Gunicorn and Railway

-----

## 🛠️ Technology Stack

| Category                  | Technology                                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Backend** | Flask 2.3.3, CrewAI, OpenAI GPT-4o, SQLite, Gunicorn                                                          |
| **Frontend** | Bootstrap 5.3.0, Chart.js, Vanilla JavaScript, Custom CSS                                                     |
| **AI & Data Processing** | LangChain, pdfplumber, Pandas, NumPy                                                                          |
| **Authentication & APIs** | Google OAuth 2.0, Google Sheets API, Google Drive API                                                         |

-----

## 📋 Prerequisites

  * Python 3.8+
  * Google Cloud Project with APIs enabled
  * OpenAI API key
  * Railway account (for production deployment)

-----

## 🚀 Quick Start

1.  **Clone the Repository**

    ```bash
    git clone https://github.com/yourusername/ism-report-analysis.git
    cd ism-report-analysis
    ```

2.  **Install Dependencies**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Setup**
    Create a `.env` file in the root directory:

    ```env
    OPENAI_API_KEY=your_openai_api_key
    SECRET_KEY=your_secret_key
    GOOGLE_CREDENTIALS_BASE64=your_base64_encoded_credentials
    ```

4.  **Google API Setup**

      - Create a Google Cloud Project
      - Enable Google Sheets and Drive APIs
      - Create OAuth 2.0 credentials
      - Download credentials JSON and encode to base64

5.  **Run the Application**

    ```bash
    # Development
    python app.py

    # Production
    gunicorn app:app --bind 0.0.0.0:$PORT
    ```

-----

## ⚙️ Configuration

### Report Types

The application supports two report types configured via JSON files:

  - **Manufacturing Reports** (`config/manufacturing_config.json`)
    ```json
    {
      "indices": [
        "Manufacturing PMI",
        "New Orders",
        "Production",
        "Employment",
        "Supplier Deliveries",
        "Inventories",
        "Customers' Inventories",
        "Prices",
        "Backlog of Orders",
        "New Export Orders",
        "Imports"
      ],
      "canonical_industries": [
        "Chemical Products",
        "Computer & Electronic Products",
        "Machinery"
      ]
    }
    ```
  - **Services Reports** (`config/services_config.json`)
    ```json
    {
      "indices": [
        "Services PMI",
        "Business Activity",
        "New Orders",
        "Employment"
      ],
      "canonical_industries": [
        "Accommodation & Food Services",
        "Finance & Insurance",
        "Health Care & Social Assistance"
      ]
    }
    ```

### Database Configuration

The application automatically detects the environment and configures the database path:

  - **Local Development:** `./ism_data.db`
  - **Railway Production:** `/data/ism_data.db` (mounted volume)

-----

## 📖 Usage

1.  **Authentication**
      - Navigate to the application URL.
      - Click "Sign in with Google".
      - Authorize the application.
2.  **Upload Reports**
      - Go to the **Upload** page.
      - Select one or more ISM PDF reports.
      - Choose visualization options.
      - Click **Upload and Process**.
3.  **View Dashboard**
      - **Heatmap Summary:** Monthly PMI values with color coding.
      - **Alphabetical View:** Industry status sorted alphabetically.
      - **Numerical View:** Industry rankings by performance.
      - **Trends:** Time-series analysis with interactive charts.
      - **Comparison:** Manufacturing vs. Services comparison tools.
4.  **Export Data**
      - Data is automatically exported to Google Sheets.
      - Access shared spreadsheets for collaboration.
      - Download data in various formats.

-----

## 🏗️ Architecture

### AI Agent System

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Document        │    │ Data Structurer  │    │ QA & Validator  │
│ Extractor Agent │───▶│ Agent            │───▶│ Agent           │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                       │
         ▼                        ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ PDF Input       │    │ Structured Data  │    │ Validated Data  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Data Flow

`PDF Upload` → `AI Extraction` → `Data Structuring` → `Validation` → `Database Storage` → `Visualization`

-----

## 🔧 API Endpoints

### Core Endpoints

  - `GET /`: Home page (redirects based on auth)
  - `GET /dashboard`: Main dashboard
  - `POST /upload`: File upload and processing
  - `GET /api/heatmap_data/<months>`: PMI heatmap data
  - `GET /api/index_trends/<index_name>`: Time series data
  - `GET /api/industry_status/<index_name>`: Industry status data

### Authentication

  - `GET /login`: Initiate Google OAuth
  - `GET /oauth2callback`: OAuth callback
  - `GET /logout`: User logout

### Report Type Support

All API endpoints support the `report_type` parameter:

  - `?report_type=Manufacturing`
  - `?report_type=Services`

-----

## 🚀 Deployment

### Railway Deployment

1.  Connect your GitHub repository to Railway.
2.  Set environment variables in the Railway dashboard.
3.  Configure the volume mount for persistent storage.
4.  Deploy with the included `railway.json` configuration.

### Environment Variables

```env
OPENAI_API_KEY=your_api_key
SECRET_KEY=your_secret_key
GOOGLE_CREDENTIALS_BASE64=your_credentials
RAILWAY_VOLUME_MOUNT_PATH=/data
```

### Health Check

The application includes a health check endpoint at `/health` for monitoring.

-----

## 🧪 Testing

### Run Tests

```bash
# Unit tests
python -m pytest tests/

# Integration tests
python -m pytest tests/integration/

# Coverage report
python -m pytest --cov=. tests/
```

### Test Report Processing

```bash
# Test with sample PDF
python main.py --pdf tests/fixtures/sample_ism_report.pdf
```

-----

## 📊 Database Schema

### Tables

  - **`reports`**: Report metadata and processing status.
  - **`pmi_indices`**: PMI index values and directions.
  - **`industry_status`**: Industry classifications by index and month.

### Key Relationships

```sql
reports (1) → (M) pmi_indices
reports (1) → (M) industry_status
```

-----

## 🤝 Contributing

### Development Setup

1.  Fork the repository.
2.  Create a feature branch: `git checkout -b feature-name`.
3.  Make your changes.
4.  Run tests: `pytest`.
5.  Submit a pull request.

### Code Style

  - Follow PEP 8 guidelines.
  - Use type hints where appropriate.
  - Add docstrings for new functions.
  - Update tests for new features.

### Agent Development

When adding new AI agents:

1.  Extend `BaseTool` from CrewAI.
2.  Implement the `_run` method.
3.  Add comprehensive error handling.
4.  Update the orchestration workflow.

-----

## 📝 Changelog

### v2.0.0 (Latest)

  - ✅ Multi-agent AI system with CrewAI
  - ✅ Services report support
  - ✅ Enhanced dashboard with comparison tools
  - ✅ Improved data validation pipeline
  - ✅ Railway deployment optimization

### v1.0.0

  - ✅ Initial release with Manufacturing report support
  - ✅ Basic AI extraction with OpenAI
  - ✅ Google Sheets integration
  - ✅ Interactive dashboard

-----

## 🐛 Troubleshooting

### Common Issues

  - **PDF Processing Fails**
      - Ensure PDF is text-readable (not a scanned image).
      - Check OpenAI API key and rate limits.
      - Verify file size is under the 16MB limit.
  - **Google Sheets Integration Issues**
      - Verify OAuth credentials are correct.
      - Check API quotas in Google Cloud Console.
      - Ensure proper scopes are authorized.
  - **Database Errors**
      - Check file permissions for the SQLite database.
      - Verify volume mounting in production.
      - Run database initialization: `python -c "from db_utils import initialize_database; initialize_database()"`

### Logging

Application logs are available in:

  - **Development:** `logs/ism_analysis.log`
  - **Production:** Railway application logs

-----

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

-----

## 🙏 Acknowledgments

  - Institute for Supply Management (ISM) for PMI data standards
  - OpenAI for the GPT-4o API
  - CrewAI for the multi-agent framework
  - Railway for the deployment platform

-----

## 📞 Support

  - 📧 **Email:** [support@yourcompany.com](mailto:support@yourcompany.com)
  - 📚 **Documentation:** Wiki
  - 🐛 **Issues:** GitHub Issues

-----

Made with ❤️ by Envoy LLC
