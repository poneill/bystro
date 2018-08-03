use 5.10.0;
use strict;
use warnings;
# TODO: Also support reading zipped files (right now only gzip files)
package Seq::Role::IO;

our $VERSION = '0.001';

# ABSTRACT: A moose role for all of our file handle needs
# VERSION

use Mouse::Role;

use PerlIO::utf8_strict;
use PerlIO::gzip;
use File::Which qw/which/;

use Path::Tiny;
use Try::Tiny;
use DDP;
use Scalar::Util qw/looks_like_number/;
with 'Seq::Role::Message';
# tried various ways of assigning this to an attrib, with the intention that
# one could change the taint checking characters allowed but this is the simpliest
# one that worked; wanted it precompiled to improve the speed of checking
our $taintCheckRegex = qr{\A([\+\,\.\-\=\:\/\t\|\s\w\d/]+)\z};

has taintCheckRegex => (
  is => 'ro',
  lazy => 1,
  init_arg => undef,
  default => sub{ $taintCheckRegex },
);

has delimiter => (
  is => 'ro',
  lazy => 1,
  default => '\t',
  writer => '_setDelimiter',
);

my $tar = which('tar');
my $gzip = which('pigz') || which('gzip');

# Without this, pigz -d -c issues many system calls (futex)
# Thanks to Meltdown, this slows decompression substantially
# Up to 1 core will be used solely for meltdown-related overhead
# So disable mutli-threading
# For compression, tradeoff still worth it
my $dcmpArgs = '-d -c';
if($gzip =~ /pigz/) {
 $dcmpArgs = "-p 1 $dcmpArgs";
}

my $tarCompressed = "$tar --use-compress-program=$gzip";

has gzip => (is => 'ro', isa => 'Str', init_arg => undef, lazy => 1, default => sub {$gzip});
has dcmpArgs => (is => 'ro', isa => 'Str', init_arg => undef, lazy => 1, default => sub {$dcmpArgs});

#@param {Path::Tiny} $file : the Path::Tiny object representing a single input file
#@param {Str} $innerFile : if passed a tarball, we will want to stream a single file within
#@return file handle
# TODO: return error, don't die
sub getReadFh {
  my ( $self, $file, $innerFile) = @_;
  my $fh;

  # Ensures that anything that hasn't been written to a file (from async process)
  # Is written
  # This behavior is most obvious with Log::Fast
  system('sync');

  if(ref $file ne 'Path::Tiny' ) {
    $file = path($file)->absolute;
  }

  my $filePath = $file->stringify;

  if (!$file->is_file) {
    $self->log('fatal', "$filePath does not exist for reading");
  }

  my $compressed = 0;
  my $err;
  if($innerFile) {
    $compressed = $innerFile =~ /\.gz$/ || $innerFile =~ /\.bgz$/ || $innerFile =~ /\.zip$/;

    my $innerCommand = $compressed ? "\"$innerFile\" | $gzip $dcmpArgs -" : "\"$innerFile\"";
    # We do this because we have not built in error handling from opening streams

    my $command;
    my $outerCompressed;
    if($filePath =~ /\.tar.gz$/) {
      $outerCompressed = 1;
      $command = "$tarCompressed -O -xf \"$filePath\" $innerCommand";
    } elsif($filePath =~ /\.tar$/) {
      $command = "$tar -O -xf \"$filePath\" $innerCommand";
    } else {
      $self->log('fatal', "When inner file provided, must provde a parent file.tar or file.tar.gz");
    }

    open ($fh, '-|', $command) or $self->log('fatal', "Failed to open $filePath ($innerFile) due to $!");

    # From a size standpoint a tarball and a tar file whose inner annotation is compressed are similar
    # since the annotation dominate
    $compressed = $compressed || $outerCompressed;
    # If an innerFile is passed, we assume that $file is a path to a tarball
  } elsif($filePath =~ /\.gz$/ || $filePath =~ /\.bgz$/ || $filePath =~ /\.zip$/) {
    $compressed = 1;
    #PerlIO::gzip doesn't seem to play nicely with MCE, reads random number of lines
    #and then exits, so use gunzip, standard on linux, and faster
    open ($fh, '-|', "$gzip $dcmpArgs \"$filePath\"") or $self->log('fatal', "Failed to open $filePath due to $!");
  } else {
    open ($fh, '<', $filePath) or $self->log('fatal', "Failed to open $filePath due to $!");
  };

  # TODO: return errors, rather than dying
  return ($err, $compressed, $fh);
}

# Is the file a single compressed file
sub isCompressedSingle {
  my ($self, $filePath) = @_;

  my $basename = path($filePath)->basename();

  if($basename =~ /tar.gz$/) {
    return 0;
  }

  return $basename =~ /\.gz$/ || $basename =~ /\.bgz$/ || $basename =~ /\.zip$/;
}

# TODO: return error if failed
sub getWriteFh {
  my ( $self, $file, $compress ) = @_;

  system('sync');

  $self->log('fatal', "get_fh() expected a filename") unless $file;

  my $fh;
  if ( $compress || $file =~ /\.gz$/ || $file =~ /\.bgz$/ || $file =~ /\.zip$/ ) {
    # open($fh, ">:gzip", $file) or die $self->log('fatal', "Couldn't open $file for writing: $!");
    open($fh, "|-", "$gzip -c > $file") or $self->log('fatal', "Couldn't open gzip $file for writing");
  } else {
    open($fh, ">", $file) or return $self->log('fatal', "Couldn't open $file for writing: $!");
  }

  return $fh;
}

sub safeOpen {
  #my ($self, $fh, $operator, $operand) = @_;
  #    $_[0], $_[1], $_[2],   $_[3]

  # Modifies $fh/$_[1] by reference
  open($_[1], $_[2], $_[3]) or $_[0]->log('fatal', "Couldn't open $_[3]: $!");

  return $_[1];
}

sub safeClose {
  #my ($self, $fh) = @_;
  #    $_[0], $_[1]

  close($_[1]) or $_[0]->log('fatal', "Couldn't close fh: $!");

  return;
}

sub getCleanFields {
  my ( $self, $line ) = @_;

  chomp $line;
  if ( $line =~ m/$taintCheckRegex/xm ) {
    my @out;

    push @out, split $self->delimiter, $1;

    return \@out;
  }
  
  return undef;
}

sub getLineEndings {
  return $/;
}

sub setLineEndings {
  my ($self, $firstLine) = @_;

  if($firstLine =~ /\r\n$/) {
    $/ = "\r\n";
  } elsif($firstLine =~ /\n$/) {
    $/ = "\n";
  } elsif($firstLine =~ /\015/) {
    # Match ^M (MacOS style line endings, which Excel outputs on Macs)
    $/ = "\015";
  } else {
    return "Cannot discern line endings: Not Mac, Unix, or Windows style";
  }

  return "";
}

sub checkDelimiter {
  my ($self, $line) = @_;

  if($line =~ /^\s*\S+\t\S+/) {
    return 1;
  }

  return 0;
}

sub setDelimiter {
  my ($self, $line) = @_;

  if($line =~ /^\s*\S+\t\S+/) {
    $self->_setDelimiter('\t');
  } elsif ($line =~ /^\s*\S+,\S+/) {
    $self->_setDelimiter(',');
  } else {
    return "Line is not tab or comma delimited";
  }

  return "";
}

sub makeTarballName {
  my ($self, $baseName, $compress) = @_;

  return $baseName . ($compress ? '.tar.gz' : '.tar');
}

# Assumes if ref's are passed for dir, baseName, or compressedName, they are path tiny
sub compressDirIntoTarball {
  my ($self, $dir, $tarballName) = @_;

  if(!$tar) { 
    $self->log( 'warn', 'No tar program found');
    return 'No tar program found';
  }

  if(ref $dir) {
    $dir = $dir->stringify;
  }
  
  if(!$tarballName) {
    $self->log('warn', 'must provide baseName or tarballName');
    return 'Must provide baseName or tarballName';
  }

  if(ref $tarballName) {
    $tarballName = $tarballName->stringify;
  }

  $self->log( 'info', 'Compressing all output files' );

  my @files = glob $dir;

  if ( !@files) {
    $self->log( 'warn', "Directory is empty" );
    return 'Directory is empty';
  }

  my $tarProg = $tarballName =~ /tar.gz$/ ? $tarCompressed : $tar;
  my $tarCommand = sprintf("cd %s; $tarProg --exclude '.*' --exclude %s -cf %s * --remove-files",
    $dir,
    $tarballName, #and don't include our new compressed file in our tarball
    $tarballName, # the name of our tarball
  );

  $self->log('debug', "compress command: $tarCommand");
    
  if(system($tarCommand) ) {
    $self->log( 'warn', "compressDirIntoTarball failed with $?" );
    return $?;
  }

  return 0;
}

sub getCompressedFileSize {
  my ($self, $filePath) = @_;

  if(!$self->isCompressedSingle($filePath)) {
    return ('Expect compressed file', undef);
  }

  open(my $fh, "-|", "$gzip -l " . path($filePath)->stringify);
  <$fh>;
  my $sizeLine = <$fh>;

  chomp $sizeLine;
  my @sizes = split(" ", $sizeLine);

  #pigz return 0? when file is larger than 4GB, gzip returns 0
  if(!$sizes[1] || !looks_like_number($sizes[1])) {
    return (undef, 0);
  }

  return (undef, $sizes[1]);
}

# returns chunk size in kbytes
sub getChunkSize {
  my ($self, $filePath, $parts) = @_;

  my $size = path($filePath)->stat()->size;

  # Files range from ~ 10 - 60x compression ratios; but large files don't report
  # correct ratios (> 4GB)
  # If file is < 4GB it will be reported correctly
  if($self->isCompressedSingle($filePath)) {
    my ($err, $compressedSize) = $self->getCompressedFileSize($filePath);

    if($err) {
      return ($err, undef);
    }

    $size = $compressedSize == 0 ? $size * 30 : $compressedSize;
  }

  my $chunkSize = CORE::int($size / ($parts * 4096));

  if ($chunkSize < 512) {
    return (undef, 512);
  }

  # Cap to make sure memory usage doesn't grow uncontrollably
  if ($chunkSize > 1536) {
    return (undef, 1536);
  }

  return (undef, $chunkSize);
}

no Mouse::Role;

1;
