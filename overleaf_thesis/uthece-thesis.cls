%%%%%%
% Template for typesetting Diploma and Master's Theses
%
% Michael Vassilakoppoulos, mvasilako@uth.gr
%
% (adapted from the TEI PELOPONNESE template for diploma theses
% [https://www.overleaf.com/latex/examples/protupo-ptuxiakis-ergasias-tmima-mixanikon-plirophorikis-te-tei-peloponnisou/fxyzzbhjkmxd]
% which was based on NTUA template for diploma theses [http://web.dbnet.ntua.gr/el/diplomas.html])
%
% Last update:  July 26, 2022
%
%%%%%%
% Class Information
\def\filename{uthece-thesis}
\def\fileversion{2.0}
\def\filedate{2022/07/26}
\NeedsTeXFormat{LaTeX2e}[1996/12/01]
\ProvidesClass{uthece-thesis}[%
    \filedate\space\fileversion\space LaTeX document class.]
% Required Packages
\RequirePackage{ifthen}
\RequirePackage{graphicx}
\RequirePackage{fancyhdr}
%\RequirePackage{epstopdf}

\newif\ifgrthesisoption
\grthesisoptionfalse

\DeclareOption{grthesis}{
 	\grthesisoptiontrue
}

\newif\ifmasterthesisoption
\masterthesisoptionfalse

\DeclareOption{masterthesis}{
 	\masterthesisoptiontrue
}

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{book}}
\ProcessOptions
\LoadClass[a4paper,12pt,twoside]{book}


% Greek Support
\usepackage[Greek,Latin]{ucharclasses}%handles mixed english-greek hyphenation
\usepackage{xgreek}
\setTransitionsForGreek{\setlanguage{greek}}{\setlanguage{american}}%handles mixed english-greek hyphenation
\usepackage[no-math]{fontspec}
\defaultfontfeatures{Mapping=tex-text}
% Math
\usepackage{amssymb,amsmath,amsthm,amsfonts} 
\usepackage{mathspec}
\setmainfont{Times New Roman}
\setmonofont{Courier New}
\setsansfont{Arial}
\pagestyle{fancy}
% Title Page and Front Matter
\def\@supervisor{} \def\supervisor#1{\gdef\@supervisor{#1}}
\def\@supervisorEng{} \def\supervisorEng#1{\gdef\@supervisorEng{#1}}
\def\@titleEng{}  \def\titleEng#1{\gdef\@titleEng{#1}}
\def\@translator{} \def\translator#1{\gdef\@translator{#1}}
\def\@institution{} \def\institution#1{\gdef\@institution{#1}}
\def\@department{} \def\department#1{\gdef\@department{#1}}
\def\@division{}  \def\division#1{\gdef\@division{#1}}
\def\@translatorO{} \def\translatorO#1{\gdef\@translatorO{#1}}
\def\@institutionO{} \def\institutionO#1{\gdef\@institutionO{#1}}
\def\@departmentO{} \def\departmentO#1{\gdef\@departmentO{#1}}
\def\@divisionO{}  \def\divisionO#1{\gdef\@divisionO{#1}}
\def\@otherO{}\def\otherO#1{\gdef\@otherO{#1}}
\def\@lab{} 
\def\lab#1{\gdef\@lab{#1}}
\def\@other{}\def\other#1{\gdef\@other{#1}}
\def\@dedication{}\def\dedication#1{\def\@dedication{#1}}
\def\@uppertitleback{} \long\def\uppertitleback#1{\def\@uppertitleback{#1}}
\def\@uppertitlebackO{} \long\def\uppertitlebackO#1{\def\@uppertitlebackO{#1}}
\def\@middletitleback{} \long\def\middletitleback#1{\def\@middletitleback{#1}}
\def\@lowertitleback{} \long\def\lowertitleback#1{\def\@lowertitleback{#1}}
\def\@approval{}\long\def\approval#1{\def\@approval{#1}}
\def\@mysig{}\long\def\mysig#1{\def\@mysig{#1}}

\def\url#1{\gdef\@url{\texttt{#1}}}
\def\TRnumber#1{\gdef\@TRnumber{#1}}
\def\@trurl{}\def\trurl#1{\gdef\@trurl{\texttt{#1}}}
\def\@trftp{}\def\trftp#1{\gdef\@trftp{\texttt{#1}}}

\def\new@tpage{\newpage\thispagestyle{empty}\null}
% Measurements
\setlength{\oddsidemargin}{5mm}
\setlength{\evensidemargin}{5mm}
\setlength{\textwidth}{155mm}

\setlength{\topmargin}{0mm}
\setlength{\textheight}{247mm}
\advance \topmargin by -\headheight
\advance \topmargin by -\headsep

\renewcommand{\numer@lsign}{$'$}

\ifgrthesisoption
% names defined by xgreek package
    \def\contentsname{Πίνακας περιεχομένων}%
\else
    \def\prefacename{Preface}%
    \def\refname{References}%
    %\def\abstractname{Abstract}%
    \def\bibname{Bibliography}%
    \def\chaptername{Chapter}%
    \def\appendixname{Appendix}%
    \def\contentsname{Table of contents}%
    \def\listfigurename{List of figures}%
    \def\listtablename{List of tables}%
    \def\indexname{Index}%
    \def\figurename{Figure}%
    \def\tablename{Table}%
    \def\partname{Part}%
    \def\enclname{Attachments}%
    \def\ccname{cc}%
    \def\headtoname{To}%
    \def\pagename{Page}%
    \def\seename{see}%
    \def\alsoname{see also}%
    \def\proofname{Proof}%
    \def\glossaryname{Glossary}%
\fi

% Maketitle
\renewcommand{\maketitle}{
    \begin{titlepage}
        \let\footnotesize\small
        \let\footnoterule\relax
        \renewcommand{\thefootnote}{\fnsymbol{footnote}}
        \new@tpage
        \begin{center}

            \begin{minipage}{3.5cm}
            \ifgrthesisoption
                \includegraphics[width=3.5cm]{logos/UTH-logo-greek.png}
            \else
                 \includegraphics[width=3.5cm]{logos/UTH-logo-english.png}
            \fi
	    	\vspace{3pt}
            \end{minipage}

            \begin{minipage}{15cm}
            \begin{center}
                \textnormal{
                \large{\@institution} \\
                {\normalsize\@department \\
                \@division \\
                \@other
                }}
            \end{center}
            \end{minipage}
            \vspace{2cm}
            \begin{center}
                \Large \bfseries 
                \ifgrthesisoption 
                    \@title
                \else
                    \@titleEng
                \fi
            \end{center}
             \vfill 
            %
            \begin{center}
                \LARGE{\textnormal{\@translator}}\\
                \vspace{3mm}                \normalsize~\\
                \vspace{3mm}
                \ifgrthesisoption 
                    \Large{\textbf{\authorname}}\\
                    \Large{\textbf{\secauthorname}}
                \else
                    \Large{\textbf{\authornameEng}}\\
                    \Large{\textbf{\secauthornameEng}}
                \fi
            \end{center}
            %
            \vspace{5mm}
            %
            \hspace{1mm}
        \end{center}

        \vfill

        \begin{flushleft}
            \large 
            \ifgrthesisoption
               \textbf{\supervisorname :}
             \else\textbf{Supervisor:}
             \fi
                \ifgrthesisoption 
                    \@supervisor\\
                \else
                    \@supervisorEng\\
                \fi
%            \supervisorTitle\\
        \end{flushleft}
        \vspace{1mm}

        %
        \vfill
        %

        \begin{center}
            \textnormal{\@lab}\\
            \ifgrthesisoption
                \thesisPlaceDate
            \else
                \thesisPlaceDateEng
            \fi
        \end{center}
        %
        \cleardoublepage
        \newpage\thispagestyle{plain} %\new@tpage
        \begin{center}

            \begin{minipage}{3.5cm}
            \ifgrthesisoption
                \includegraphics[width=3.5cm]{logos/UTH-logo-greek.png}
            \else
                 \includegraphics[width=3.5cm]{logos/UTH-logo-english.png}
            \fi
	    	\vspace{3pt}
            \end{minipage}

            \begin{minipage}{15cm}
            \begin{center}
                \textnormal{
                \large{\@institution} \\
                {\normalsize\@department \\
                \@division \\
                \@other
                }}
            \end{center}
            \end{minipage}
            \vspace{2cm}
            \begin{center}
                \Large \bfseries 
                \ifgrthesisoption 
                    \@title
                \else
                    \@titleEng
                \fi
            \end{center}
            \vfill
            %
            \begin{center}
                \LARGE{\textnormal{\@translator}}\\
                \vspace{3mm}                
                \normalsize~\\
                \vspace{3mm}
                \ifgrthesisoption 
                    \Large{\textbf{\authorname}}\\
                    \Large{\textbf{\secauthorname}}
                \else
                    \Large{\textbf{\authornameEng}}\\
                    \Large{\textbf{\secauthornameEng}}
                \fi
            \end{center}
            %
            \vspace{5mm}
            %
            \hspace{1mm}
        \end{center}

        \vfill

        \begin{flushleft}
            \large 
            \ifgrthesisoption
               \textbf{\supervisorname :}
             \else\textbf{Supervisor:}
             \fi
                \ifgrthesisoption 
                    \@supervisor\\
                \else
                    \@supervisorEng\\
                \fi
%            \supervisorTitle\\
        \end{flushleft}
        \vspace{1mm}

        %
        \vfill
        %

        \begin{center}
            \textnormal{\@lab}\\
            \ifgrthesisoption
                \thesisPlaceDate
            \else
                \thesisPlaceDateEng
            \fi
        \end{center}
        \cleardoublepage
        \newpage\thispagestyle{plain} %\new@tpage
        \begin{center}

            \begin{minipage}{3.5cm}
            \ifgrthesisoption
                \includegraphics[width=3.5cm]{logos/UTH-logo-english.png}
            \else
                 \includegraphics[width=3.5cm]{logos/UTH-logo-greek.png}
            \fi
	    	\vspace{3pt}
            \end{minipage}

            \begin{minipage}{15cm}
            \begin{center}
                \textnormal{
                \large{\@institutionO} \\
                {\normalsize\@departmentO \\
                \@divisionO \\
                \@otherO
                }}
            \end{center}
            \end{minipage}
            \vspace{2cm}
            \begin{center}
                \Large \bfseries 
                \ifgrthesisoption 
                    \@titleEng
                \else
                    \@title
                \fi            
            \end{center}
            \vfill
            %
            \begin{center}
                \LARGE{\textnormal{\@translatorO}}\\
                \vspace{3mm}                \normalsize~\\%{\ifgrthesisoption\toutis\else by\fi}\\
                \vspace{3mm}
                \ifgrthesisoption 
                    \Large{\textbf{\authornameEng}}\\
                    \Large{\textbf{\secauthornameEng}}
                \else
                    \Large{\textbf{\authorname}}\\
                    \Large{\textbf{\secauthorname}}
                \fi
            \end{center}
            %
            \vspace{5mm}
            %
            \hspace{1mm}
        \end{center}

        \vfill

        \begin{flushleft}
            \large 
            \ifgrthesisoption
               \textbf{Supervisor:}
             \else\textbf{\supervisorname :}
             \fi
            \ifgrthesisoption 
                \@supervisorEng\\
            \else
                \@supervisor\\
            \fi
%            \supervisorTitleO\\
        \end{flushleft}
        \vspace{1mm}

        %
        \vfill
        %

        \begin{center}
            \textnormal{\@lab}\\
            \ifgrthesisoption
                \thesisPlaceDateEng
            \else
                \thesisPlaceDate
            \fi
        \end{center}
        %%%%
        \cleardoublepage
        \newpage\thispagestyle{plain}
        \vspace*{3cm}
        \begin{flushleft}
        \begin{tabular}{l}
        \ifgrthesisoption
            \noindent Εγκρίνεται από την Επιτροπή Εξέτασης:
        \else
            \noindent Approved by the Examination Committee:
        \fi
        \end{tabular}
        \vspace{1.5cm}
        
        \begin{tabular}{ll}
        \ifgrthesisoption \supervisorMaleFemale \else Supervisor \fi
        & \begin{minipage}[t]{0.75\textwidth}
           \ifgrthesisoption {\textbf \@supervisor}
           \else {\textbf \@supervisorEng} \fi\\
           \supervisortitle, \supervisoraffiliation
          \end{minipage}\\\\
        \ifgrthesisoption Μέλος \else Member \fi
        & \begin{minipage}[t]{0.75\textwidth}
           {\textbf\memberonename}\\
           \memberonetitle, \memberoneaffiation
          \end{minipage}\\\\
        \ifgrthesisoption Μέλος \else Member \fi
        & \begin{minipage}[t]{0.75\textwidth}
           {\textbf\membertwoname}\\
           \membertwotitle, \membertwoaffiation
          \end{minipage}
        \end{tabular}
        \end{flushleft}
        \vspace{1cm}
        
        % \ifgrthesisoption \noindent Ημερομηνία έγκρισης:
        % \else
        %     \noindent Date of approval:
        % \fi \displaydate{docapprovedate}
        %%%%%%%
        \IfFileExists{acknowledgements}{\include{acknowledgements}}{}
        \cleardoublepage
        \ifgrthesisoption
            \include{declaration}
        \else
            \include{declaration_eng}
        \fi	
        % Περίληψη
        \ifgrthesisoption
	        \include{abstract}
	    \include{abstract_eng}
        \else
	        \include{abstract_eng}
	        \include{abstract}
        \fi
        % Πίνακας Περιεχομένων
	    \tableofcontents
%%%%
    \end{titlepage}
    %
    \renewcommand{\thefootnote}{\arabic{footnote}}
    \setcounter{footnote}{0}
    %
%    \gdef\@thanks{}\gdef\@author{}\gdef\@translator{}\gdef\@institution{}
    \gdef\@department{}\gdef\@division{}\gdef\@lab{}\gdef\@other{}
    \gdef\@uppertitleback{}\gdef\@lowertitleback{}\gdef\@dedication{}%
    \gdef\@uppertitlebackO{}\gdef\@lowertitleback{}\gdef\@dedication{}%
}

\usepackage{emptypage}
\usepackage{indentfirst}
\usepackage{verbatim}
\usepackage{latexsym}
\bibliographystyle{unsrt}
\usepackage[nottoc]{tocbibind}

\ifgrthesisoption
    \newtheorem{definition}{Ορισμός}
    \newtheorem{proposition}{Πρόταση}
    \newtheorem{theorem}{Θεώρημα}
    \newtheorem{corollary}{Πόρισμα}
    \newtheorem{lemma}{Λήμμα}
    \newtheorem{example}{Παράδειγμα}
    \newtheorem{remark}{Σημείωση}
    \newtheorem{notation}{Συμβολισμός}
    \newtheorem{law}{Νόμος}
\else
    \newtheorem{definition}{Definition}
    \newtheorem{proposition}{Proposition}
    \newtheorem{theorem}{Theorem}
    \newtheorem{corollary}{Corollary}
    \newtheorem{lemma}{Lemma}
    \newtheorem{example}{Example}
    \newtheorem{remark}{Remark}
    \newtheorem{notation}{Notation}
    \newtheorem{law}{Law}
\fi
\renewcommand{\thedefinition}{\arabic{chapter}.\arabic{definition}}
\renewcommand{\theproposition}{\arabic{chapter}.\arabic{proposition}}
\renewcommand{\thetheorem}{\arabic{chapter}.\arabic{theorem}}
\renewcommand{\thecorollary}{\arabic{chapter}.\arabic{corollary}}
\renewcommand{\thelemma}{\arabic{chapter}.\arabic{lemma}}
\renewcommand{\theexample}{\arabic{chapter}.\arabic{example}}
\newcommand{\set}[1]{\left\{#1\right\}}
\newcommand{\To}{\Longrightarrow}
\newcommand{\xml}{\en{XML}}

% Names
\newcommand{\urlname}{{URL}}
\newcommand{\ftpname}{{FTP}}
\newcommand{\abstractnameeng}{{Abstract}}
\newcommand{\keywordsnameeng}{{Keywords}}
\newcommand{\supervisorname}{\supervisorMaleFemale}
\newcommand{\keywordsname}{Λέξεις Κλειδιά}

\newcommand{\programme}{}
\newcommand{\beforeprogramme}{}
\newcommand{\programmeO}{}
\newcommand{\beforeprogrammeO}{}
% More Names

\ifgrthesisoption
%   \newcommand{\keywordsname}{Λέξεις Κλειδιά}
    \newcommand{\draftname}{Προσχέδιο}
    \newcommand{\acknowledgementsname}{Ευχαριστίες}
    \newcommand{\pagesname}{Σελίδες}
    \ifmasterthesisoption
        \translator{Μεταπτυχιακή Διπλωματική Εργασία}
    \else
        \translator{Διπλωματική Εργασία}
    \fi
    \institution{ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ}
    \department{ΠΟΛΥΤΕΧΝΙΚΗ ΣΧΟΛΗ}
     \division{ΤΜΗΜΑ ΗΛΕΚΤΡΟΛΟΓΩΝ ΜΗΧΑΝΙΚΩΝ ΚΑΙ ΜΗΧΑΝΙΚΩΝ ΥΠΟΛΟΓΙΣΤΩΝ}
     \ifmasterthesisoption
     \other{Πρόγραμμα Μεταπτυχιακών Σπουδών \beforeprogramme\\\programme}
     \fi
    \ifmasterthesisoption
        \translatorO{Master's Thesis}
    \else
        \translatorO{Diploma Thesis}
    \fi
    \institutionO{UNIVERSITY OF THESSALY}
    \departmentO{SCHOOL OF ENGINEERING}
     \divisionO{DEPARTMENT OF ELECTRICAL AND COMPUTER ENGINEERING}
     \ifmasterthesisoption
     \otherO{Programme of MSc Studies \beforeprogrammeO\\\programmeO}
     \fi
\else
%   \newcommand{\keywordsname}{Keywords}
    \newcommand{\draftname}{Draft}
    \newcommand{\acknowledgementsname}{Acknowledgements}
    \newcommand{\pagesname}{Pages}
    \ifmasterthesisoption
        \translator{Master's Thesis}
    \else
        \translator{Diploma Thesis}
    \fi
    \institution{UNIVERSITY OF THESSALY}
    \department{SCHOOL OF ENGINEERING}
     \division{DEPARTMENT OF ELECTRICAL AND COMPUTER ENGINEERING}
     \ifmasterthesisoption
     \other{Programme of MSc Studies \beforeprogramme\\\programme}
     \fi
    \ifmasterthesisoption
        \translatorO{Μεταπτυχιακή Διπλωματική Εργασία}
    \else
        \translatorO{Διπλωματική Εργασία}
    \fi
    \institutionO{ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ}
    \departmentO{ΠΟΛΥΤΕΧΝΙΚΗ ΣΧΟΛΗ}
     \divisionO{ΤΜΗΜΑ ΗΛΕΚΤΡΟΛΟΓΩΝ ΜΗΧΑΝΙΚΩΝ ΚΑΙ ΜΗΧΑΝΙΚΩΝ ΥΠΟΛΟΓΙΣΤΩΝ}
     \ifmasterthesisoption
     \otherO{Πρόγραμμα Μεταπτυχιακών Σπουδών \beforeprogrammeO\\\programmeO}
     \fi
\fi


\uppertitleback{
    \begin{minipage}[c]{2cm}
        \ifgrthesisoption
            \includegraphics[width=2cm]{logos/UTH-logo-greek.png}
        \else
             \includegraphics[width=2cm]{logos/UTH-logo-english.png}
        \fi
    \end{minipage}
    \hspace{0.2cm}
    \begin{minipage}[c]{12.685cm}
        \@institution \\
        \@department \\
        \@division
        \ifmasterthesisoption
        \\\@other
        \fi
    \end{minipage}
}

\uppertitlebackO{
    \begin{minipage}[c]{2cm}
        \ifgrthesisoption
             \includegraphics[width=2cm]{logos/UTH-logo-english.png}            
        \else
             \includegraphics[width=2cm]{logos/UTH-logo-greek.png}
        \fi
    \end{minipage}
    \hspace{0.2cm}
    \begin{minipage}[c]{12.685cm}
        \@institutionO \\
        \@departmentO \\
        \@divisionO
        \ifmasterthesisoption
        \\\@otherO
        \fi
    \end{minipage}
}


% spacing
\renewcommand{\baselinestretch}{1.5}

% Redefining Commands
\renewcommand{\frontmatter}{
    \cleardoublepage
    \@mainmatterfalse \pagenumbering{roman}
}
\renewcommand{\mainmatter}{
    \label{lastfront}
    \cleardoublepage
    \@mainmattertrue\pagenumbering{arabic}
    \addtocontents{toc}{\protect\addvspace{1em}}
}
\renewcommand{\backmatter}{
    \if@openright\cleardoublepage\else\clearpage\fi
    \@mainmatterfalse
}
% Headings
\def\invisiblethingie{\tiny\ }
\def\myemptypage{
    \mbox{}
    \vspace{\fill}
    \begin{flushright}
        \invisiblethingie
    \end{flushright}
    \vspace{5ex}
    \thispagestyle{empty}
}
%
\renewcommand{\cleardoublepage}{
    \clearpage %
    \if@twoside \ifodd\c@page\else
    \myemptypage
    \newpage
    \if@twocolumn\mbox{}\newpage\fi\fi\fi
}
%
\renewcommand{\chaptermark}[1]{
    \markboth{\mbox{\@chapapp}\ \thechapter.\ \ #1}{}
%        \markboth{\mbox{\@chapapp}\ \thechapter.\ \ #1}{}
}
\renewcommand{\sectionmark}[1]{
    \markright{\thesection\ \ #1}{}
}
%
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[LO]{\slshape\nouppercase{{\rightmark}}}
\fancyhead[RE]{\slshape\nouppercase{{\leftmark}}}
\addtolength{\headheight}{3pt}
\setlength{\headwidth}{\textwidth}
%\addtolength{\topmargin}{-2pt}
%
\let\finik@tocont\tableofcontents
\renewcommand{\tableofcontents}{
    \cleardoublepage
    \addcontentsline{toc}{chapter}{\contentsname}
    \finik@tocont
}

\let\finik@lof\listoffigures
\renewcommand{\listoffigures}{
    \finik@lof
}
\let\finik@lot\listoftables
\renewcommand{\listoftables}{
    \finik@lot
}
% More Enviroments
\newenvironment{keywords}{\section*{\keywordsname}}{}
\newenvironment{keywordseng}{\section*{\keywordsnameeng}}{}
\newcommand{\footacknowledgement}[1]{%
  \let\@tmp@makefntext\@makefntext%
  \long\def\@makefntext##1{%
      \parindent 1em%
      \noindent##1}%
  \footnotetext{#1}%
  \let\@makefntext\@tmp@makefntext%
}
\newenvironment{acknowledgements}{%
  \chapter*{\acknowledgementsname}%
  \addcontentsline{toc}{chapter}{\acknowledgementsname}%
}{}
\newenvironment{abbreviations}{%
\ifgrthesisoption
  \chapter*{Συντομογραφίες}%
  \addcontentsline{toc}{chapter}{Συντομογραφίες}%
\else
  \chapter*{Abbreviations}%
  \addcontentsline{toc}{chapter}{Abbreviations}%
\fi
}{}
\newenvironment{preface}{%
  \chapter*{\prefacename}%
  \addcontentsline{toc}{chapter}{\prefacename}%
}{}
\newenvironment{terminology}{%
\ifgrthesisoption
  \chapter*{Ορολογία - Γλωσσάρι}%
  \addcontentsline{toc}{chapter}{Ορολογία - Γλωσσάρι}%
\else
  \chapter*{Glossary}%
  \addcontentsline{toc}{chapter}{Glossary}%
\fi
}{}
\def\abstract{%
%   \chapter*{\abstractname\@mkboth{\abstractname}{\abstractname}}
%   \addcontentsline{toc}{chapter}{\abstractname}
\@mkboth{\abstractname}{\abstractname}
\addcontentsline{toc}{chapter}{\abstractname}
\begin{center}
\ifgrthesisoption
    \Large\@translator\\[0.1\baselineskip]
\else
    \Large\@translatorO\\[0.1\baselineskip]
\fi
    \large{\bf\@title}\\[0.2\baselineskip]
    \large{\bf \authorname}\\
    \large{\bf \secauthorname}
\end{center}
\noindent{\LARGE\bf\abstractname}\\[\baselineskip]
}
\def\abstracteng{
%  \chapter*{\abstractnameeng\@mkboth{\abstractnameeng}{\abstractnameeng}}
%  \addcontentsline{toc}{chapter}{\abstractnameeng}
\@mkboth{\abstractnameeng}{\abstractnameeng}
\addcontentsline{toc}{chapter}{\abstractnameeng}
\begin{center}
\ifgrthesisoption
    \Large\@translatorO\\[0.1\baselineskip]
\else
    \Large\@translator\\[0.1\baselineskip]
\fi
    \large{\bf\@titleEng}\\[0.2\baselineskip]
    \large{\bf \authornameEng}\\
    \large{\bf \secauthornameEng}
\end{center}
\noindent{\LARGE\bf\abstractnameeng}\\[\baselineskip]
}
% \def\abstract{%
%   \chapter*{\abstractname\@mkboth{\abstractname}{\abstractname}}
%   \addcontentsline{toc}{chapter}{\abstractname}
% }
% \def\abstracteng{
%   \chapter*{\abstractnameeng\@mkboth{\abstractnameeng}{\abstractnameeng}}
%   \addcontentsline{toc}{chapter}{\abstractnameeng}
% }
\def\endabstract{\par\vfil\null\endtitlepage}
\def\endabstracteng{\par\vfil\null\endtitlepage}
%
\let\finik@bibl\bibliography%#1

% Misc

%\AtEndDocument{\subparagraph{}\label{lastback}}




\endinput