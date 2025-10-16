class Testmcpy < Formula
  include Language::Python::Virtualenv

  desc "MCP Testing Framework - Test LLM tool calling with MCP services"
  homepage "https://github.com/preset-io/testmcpy"
  url "https://github.com/preset-io/testmcpy/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "Apache-2.0"

  depends_on "python@3.11"

  resource "typer" do
    url "https://files.pythonhosted.org/packages/typer-0.19.2.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/rich-14.1.0.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/pyyaml-6.0.3.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/httpx-0.28.1.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "anthropic" do
    url "https://files.pythonhosted.org/packages/anthropic-0.71.0.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "fastmcp" do
    url "https://files.pythonhosted.org/packages/fastmcp-2.12.4.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  resource "python-dotenv" do
    url "https://files.pythonhosted.org/packages/python-dotenv-1.1.1.tar.gz"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  # Add other dependencies as needed

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"testmcpy", "--help"
  end
end
