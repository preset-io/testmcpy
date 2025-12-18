import React, { useState } from 'react';
import MCPProfileSelector from '../components/MCPProfileSelector';
import { LLMProfileSelector } from '../components/LLMProfileSelector';
import { TestProfileSelector } from '../components/TestProfileSelector';

const ProfilesManager = () => {
  const [activeTab, setActiveTab] = useState('mcp');
  const [mcpProfile, setMcpProfile] = useState(null);
  const [llmProfile, setLlmProfile] = useState(null);
  const [testProfile, setTestProfile] = useState(null);

  const tabs = [
    { id: 'mcp', label: 'MCP Servers', icon: '🔌' },
    { id: 'llm', label: 'LLM Providers', icon: '🤖' },
    { id: 'test', label: 'Test Configs', icon: '🧪' },
  ];

  return (
    <div className="profiles-manager">
      <div className="page-header">
        <h1>Profile Management</h1>
        <p className="page-description">
          Manage your MCP servers, LLM providers, and test configurations
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="tabs-container">
        <div className="tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-label">{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'mcp' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h2>MCP Server Profiles</h2>
              <p>
                Configure MCP server connections with authentication. Define different profiles
                for development, staging, and production environments.
              </p>
            </div>
            <MCPProfileSelector
              onProfileChange={setMcpProfile}
              currentProfile={mcpProfile}
            />
            <div className="panel-footer">
              <div className="info-box">
                <strong>Configuration File:</strong> <code>.mcp_services.yaml</code>
              </div>
              <div className="info-box">
                <strong>CLI Command:</strong> <code>testmcpy profiles</code>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'llm' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h2>LLM Provider Profiles</h2>
              <p>
                Configure LLM providers and models. Switch between different providers like
                Anthropic, OpenAI, Ollama, or local models based on your needs.
              </p>
            </div>
            <LLMProfileSelector
              onProfileChange={setLlmProfile}
              currentProfile={llmProfile}
            />
            <div className="panel-footer">
              <div className="info-box">
                <strong>Configuration File:</strong> <code>.llm_providers.yaml</code>
              </div>
              <div className="info-box">
                <strong>CLI Command:</strong> <code>testmcpy llm-profiles</code>
              </div>
              <div className="info-box">
                <strong>Example Profiles:</strong> dev (fast models), prod (best quality), budget (cost-optimized), local (no API costs)
              </div>
            </div>
          </div>
        )}

        {activeTab === 'test' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h2>Test Configuration Profiles</h2>
              <p>
                Configure test suites for different scenarios. Define test directories,
                evaluators, timeouts, and execution settings.
              </p>
            </div>
            <TestProfileSelector
              onProfileChange={setTestProfile}
              currentProfile={testProfile}
            />
            <div className="panel-footer">
              <div className="info-box">
                <strong>Configuration File:</strong> <code>.test_profiles.yaml</code>
              </div>
              <div className="info-box">
                <strong>CLI Command:</strong> <code>testmcpy test-profiles</code>
              </div>
              <div className="info-box">
                <strong>Example Profiles:</strong> unit (fast tests), integration (comprehensive), smoke (quick validation), e2e (full workflows)
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Current Selection Summary */}
      <div className="current-selection">
        <h3>Current Selection</h3>
        <div className="selection-grid">
          <div className="selection-item">
            <span className="selection-label">MCP Profile:</span>
            <span className="selection-value">{mcpProfile || 'Not selected'}</span>
          </div>
          <div className="selection-item">
            <span className="selection-label">LLM Profile:</span>
            <span className="selection-value">{llmProfile || 'Not selected'}</span>
          </div>
          <div className="selection-item">
            <span className="selection-label">Test Profile:</span>
            <span className="selection-value">{testProfile || 'Not selected'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProfilesManager;
